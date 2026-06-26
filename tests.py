from datetime import datetime, timedelta
from pathlib import Path
import io
import unittest
import importlib
from app import app, db
from sqlalchemy import func
from sqlalchemy.sql.functions import coalesce
from app.models import User, Post, Game, Bet, Winnerbet, Team
from app.forms import validate_bet_scores
from app.routes import (
    get_next_game,
    get_user_stats,
    utcnow,
    winner_bet_points_for,
    everyone_accuracy_averages,
    _user_bets_for_profile,
)
from app.teams import get_team_name, _team_names_for_sport
from app.team_data import iter_team_rows
from app.scoring import (
    grade_bet,
    compute_bet_points,
    apply_bet_scoring,
    point_values,
)
from app.chart_data import build_home_chart_data


def _switch_db_uri(uri):
    """Point SQLAlchemy at a different database without touching app.db."""
    db.session.remove()
    engines = db._app_engines.setdefault(app, {})
    for engine in engines.values():
        engine.dispose()
    engines.clear()
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    engine_options = dict(app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}))
    engine_options['url'] = uri
    engine_options.setdefault('echo', app.config.get('SQLALCHEMY_ECHO', False))
    engine_options.setdefault('echo_pool', app.config.get('SQLALCHEMY_ECHO', False))
    db._apply_driver_defaults(engine_options, app)
    engines[None] = db._make_engine(None, engine_options, app)


class TestCaseBase(unittest.TestCase):
    def setUp(self):
        self._saved_db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app_context = app.app_context()
        self.app_context.push()
        _switch_db_uri('sqlite://')
        db.create_all()
        self._original_sport = app.config['SPORT']

    def tearDown(self):
        app.config['SPORT'] = self._original_sport
        db.session.remove()
        db.drop_all()
        _switch_db_uri(self._saved_db_uri)
        self.app_context.pop()

    def set_sport(self, sport):
        app.config['SPORT'] = sport

    def make_user(self, username='player', **kwargs):
        user = User(username=username, email=f'{username}@example.com', **kwargs)
        user.set_password('cat')
        db.session.add(user)
        db.session.commit()
        return user

    def login(self, client, user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True


class ScoringRulesCase(TestCaseBase):
    """Point totals must match rules.html for hockey and football."""

    def _points(self, sport, fg, winner, diff, exact):
        return compute_bet_points(sport, fg, winner, diff, exact)

    def test_hockey_point_breakdown_matches_rules(self):
        self.set_sport('hockey')
        pts = point_values('hockey')
        self.assertEqual(pts['outcome'], 3)
        self.assertEqual(pts['score_diff'], 1)
        self.assertEqual(pts['exact_score'], 3)
        self.assertEqual(pts['first_goal'], 1)
        self.assertEqual(self._points('hockey', False, True, False, False), 3)
        self.assertEqual(self._points('hockey', False, True, True, False), 4)
        self.assertEqual(self._points('hockey', False, True, True, True), 7)
        self.assertEqual(self._points('hockey', True, True, True, True), 8)

    def test_football_point_breakdown_matches_rules(self):
        self.set_sport('football')
        pts = point_values('football')
        self.assertEqual(pts['outcome'], 2)
        self.assertEqual(pts['score_diff'], 1)
        self.assertEqual(pts['exact_score'], 3)
        self.assertEqual(pts['first_goal'], 1)
        self.assertEqual(self._points('football', False, True, False, False), 2)
        self.assertEqual(self._points('football', False, True, True, False), 3)
        self.assertEqual(self._points('football', False, True, True, True), 6)
        self.assertEqual(self._points('football', True, True, True, True), 7)

    def test_score_diff_only_counts_when_outcome_correct(self):
        game = Game(team_a='A', team_b='B', score_a=1, score_b=3, first_goal=2)
        bet = Bet(score_a=3, score_b=1, first_goal=1)
        grade_bet(bet, game)
        self.assertFalse(bet.winner_correct)
        self.assertFalse(bet.score_diff_correct)
        self.assertEqual(compute_bet_points('hockey', bet.first_goal_correct,
                                             bet.winner_correct,
                                             bet.score_diff_correct,
                                             bet.score_correct), 0)

    def test_apply_bet_scoring_on_finished_game(self):
        game = Game(team_a='CAN', team_b='USA', score_a=2, score_b=1, first_goal=1)
        bet = Bet(score_a=2, score_b=1, first_goal=1)
        apply_bet_scoring(bet, game, 'football')
        self.assertTrue(bet.score_correct)
        self.assertTrue(bet.winner_correct)
        self.assertTrue(bet.score_diff_correct)
        self.assertTrue(bet.first_goal_correct)
        self.assertEqual(bet.points, 7)


class ValidateBetScoresCase(TestCaseBase):
    def test_rejects_invalid_first_goal_for_scoreline(self):
        self.assertIsNotNone(validate_bet_scores(0, 0, 1, 'hockey'))
        self.assertIsNotNone(validate_bet_scores(1, 0, 2, 'hockey'))
        self.assertIsNotNone(validate_bet_scores(2, 1, 0, 'hockey'))

    def test_rejects_hockey_draw(self):
        self.assertIsNotNone(validate_bet_scores(2, 2, 0, 'hockey'))

    def test_allows_football_draw(self):
        self.assertIsNone(validate_bet_scores(1, 1, 1, 'football'))

    def test_allows_valid_hockey_prediction(self):
        self.assertIsNone(validate_bet_scores(3, 1, 1, 'hockey'))


class WinnerBetPointsCase(TestCaseBase):
    def test_returns_tier_points_before_deadline(self):
        user = self.make_user('hektor')
        user.final_winner = 'FIN'
        user.final_winner_timestamp = utcnow() - timedelta(days=1)
        db.session.add(Winnerbet(description='Early', last_bet=utcnow(), bet_points=10))
        db.session.add(Winnerbet(description='Late', last_bet=utcnow() + timedelta(days=7), bet_points=5))
        db.session.commit()
        self.assertEqual(winner_bet_points_for(user), 10)

    def test_returns_zero_after_all_deadlines(self):
        user = self.make_user('late')
        user.final_winner = 'FIN'
        user.final_winner_timestamp = utcnow() + timedelta(days=1)
        db.session.add(Winnerbet(description='Closed', last_bet=utcnow(), bet_points=7))
        db.session.commit()
        self.assertEqual(winner_bet_points_for(user), 0)


class ProfileRoutesCase(TestCaseBase):
    def test_legacy_routes_redirect_to_profile_setup(self):
        user = self.make_user('Hektor')
        with app.test_client() as client:
            self.login(client, user)
            for path, setup in [
                ('/edit_profile', 'profile'),
                ('/default_prediction', 'default'),
                ('/winner_prediction', 'winner'),
            ]:
                response = client.get(path, follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn(f'/user/Hektor?setup={setup}', response.location)

    def test_user_page_shows_tournament_winner_pick(self):
        user = self.make_user('Hektor')
        user.final_winner = 'FIN'
        user.final_winner_timestamp = utcnow() - timedelta(hours=1)
        db.session.add(Winnerbet(description='Tournament winner',
                                 last_bet=utcnow() + timedelta(days=1),
                                 bet_points=7))
        db.session.commit()

        with app.test_client() as client:
            self.login(client, user)
            response = client.get(f'/user/{user.username}')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'dashboard-winner-team', response.data)
        self.assertIn(b'FIN', response.data)
        self.assertIn(b'Worth 7 points', response.data)

    def test_setup_query_opens_correct_profile_section(self):
        user = self.make_user('Hektor')
        with app.test_client() as client:
            self.login(client, user)
            response = client.get(f'/user/{user.username}?setup=default')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="default-bet"', response.data)
        self.assertIn(b"openInlineForm('default-bet', true)", response.data)

    def test_profile_shows_default_bets_in_game_cards(self):
        viewer = self.make_user('viewer')
        player = self.make_user('player')
        finished_game = Game(team_a='CAN', team_b='USA',
                             starts_at=utcnow() - timedelta(days=1),
                             score_a=2, score_b=1, first_goal=1)
        upcoming_game = Game(team_a='FIN', team_b='SWE',
                             starts_at=utcnow() + timedelta(days=1))
        db.session.add_all([finished_game, upcoming_game])
        db.session.flush()
        db.session.add_all([
            Bet(user_id=player.id, game_id=finished_game.id, score_a=1, score_b=1,
                first_goal=1, is_default_bet=True),
            Bet(user_id=player.id, game_id=upcoming_game.id, score_a=0, score_b=0,
                first_goal=0, is_default_bet=True),
        ])
        db.session.commit()

        with app.test_request_context():
            from flask_login import login_user
            login_user(viewer)
            other_bets = list(_user_bets_for_profile(player))
            self.assertEqual(len(other_bets), 1)
            self.assertTrue(other_bets[0].is_default_bet)

            login_user(player)
            own_bets = list(_user_bets_for_profile(player))
            self.assertEqual(len(own_bets), 2)
            self.assertTrue(all(bet.is_default_bet for bet in own_bets))

        with app.test_client() as client:
            self.login(client, viewer)
            response = client.get(f'/user/{player.username}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'game-card--default', response.data)
        self.assertNotIn(b'chip--default-badge', response.data)


class PwaRoutesCase(TestCaseBase):
    def test_manifest_is_valid_json(self):
        with app.test_client() as client:
            response = client.get('/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/manifest+json', response.content_type)
        data = response.get_json()
        self.assertEqual(data['name'], 'Sport Predictions')
        self.assertEqual(len(data['icons']), 2)

    def test_service_worker_is_served(self):
        with app.test_client() as client:
            response = client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'sport-predictions-pwa', response.data)


class GamesPageCase(TestCaseBase):
    def test_games_page_includes_accuracy_stats(self):
        user = self.make_user('player')
        game = Game(team_a='CAN', team_b='USA',
                    starts_at=utcnow() - timedelta(days=1),
                    score_a=2, score_b=1, first_goal=1)
        db.session.add(game)
        db.session.flush()
        bet = Bet(user_id=user.id, game_id=game.id, score_a=2, score_b=1,
                  first_goal=1, is_default_bet=False)
        apply_bet_scoring(bet, game, 'football')
        db.session.add(bet)
        db.session.commit()

        with app.test_client() as client:
            self.login(client, user)
            response = client.get(f'/games/{game.id}')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'games-stats', response.data)
        self.assertIn(b'game-card-list--by-user', response.data)
        self.assertIn(b'+7', response.data)

    def test_place_predictions_orders_games_by_start_time(self):
        user = self.make_user('player')
        later = Game(team_a='CAN', team_b='USA',
                   starts_at=utcnow() + timedelta(days=2))
        sooner = Game(team_a='FIN', team_b='SWE',
                      starts_at=utcnow() + timedelta(days=1))
        db.session.add_all([later, sooner])
        db.session.commit()

        with app.test_client() as client:
            self.login(client, user)
            response = client.get('/place_predictions')

        self.assertEqual(response.status_code, 200)
        body = response.data.decode('utf-8')
        self.assertLess(body.index('FIN'), body.index('CAN'))


class EveryoneStatsCase(TestCaseBase):
    def test_everyone_accuracy_averages(self):
        self.make_user('a', is_shown=True, total_first_goal=2,
                       total_winner=4, total_score_diff=3, total_score=1,
                       total_closed_bets=10)
        self.make_user('b', is_shown=True, total_first_goal=0,
                       total_winner=2, total_score_diff=1, total_score=1,
                       total_closed_bets=10)
        self.make_user('hidden', is_shown=False, total_first_goal=10,
                       total_winner=10, total_score_diff=10, total_score=10,
                       total_closed_bets=10)
        self.assertEqual(User.query.filter(User.is_shown.is_(True)).count(), 2)

        shown_closed_bets = 20
        averages = everyone_accuracy_averages()
        self.assertEqual(averages['first_goal'], int(round(2 * 100 / shown_closed_bets)))
        self.assertEqual(averages['outcome'], int(round(6 * 100 / shown_closed_bets)))
        self.assertEqual(averages['score_diff'], int(round(4 * 100 / shown_closed_bets)))
        self.assertEqual(averages['score'], int(round(2 * 100 / shown_closed_bets)))

    def test_standings_tiebreaker_order_matches_rules(self):
        from sqlalchemy import func
        from sqlalchemy.sql.functions import coalesce
        leader = self.make_user('leader', overall_points=20, total_score=5,
                                total_score_diff=4, total_winner=3,
                                total_first_goal=2, total_closed_bets=10)
        runner = self.make_user('runner', overall_points=20, total_score=4,
                                total_score_diff=5, total_winner=3,
                                total_first_goal=2, total_closed_bets=10)
        db.session.commit()

        ranked = db.session.query(
            User.username,
            func.rank().over(order_by=(
                coalesce(User.overall_points, 0).desc(),
                coalesce(User.total_score, 0).desc(),
                coalesce(User.total_score_diff, 0).desc(),
                coalesce(User.total_winner, 0).desc(),
                coalesce(User.total_first_goal, 0).desc(),
            )).label('ranking'),
        ).order_by('ranking').all()

        self.assertEqual(ranked[0].username, 'leader')
        self.assertEqual(ranked[1].username, 'runner')

    def test_get_user_stats_returns_global_rank(self):
        self.make_user('leader', overall_points=30, total_score=5,
                       total_score_diff=4, total_winner=3,
                       total_first_goal=2, total_closed_bets=10)
        self.make_user('runner', overall_points=20, total_score=4,
                       total_score_diff=5, total_winner=3,
                       total_first_goal=2, total_closed_bets=10)
        db.session.commit()

        self.assertEqual(get_user_stats('leader').ranking, 1)
        self.assertEqual(get_user_stats('runner').ranking, 2)


class UserModelCase(TestCaseBase):
    def test_password_hashing(self):
        u = User(username='susan')
        u.set_password('cat')
        self.assertFalse(u.check_password('dog'))
        self.assertTrue(u.check_password('cat'))

    def test_avatar(self):
        u = User(username='john', email='john@example.com')
        self.assertEqual(u.avatar(128), ('https://www.gravatar.com/avatar/'
                                         'd4c74594d841139328695756648b6bd6'
                                         '?d=identicon&s=128'))

    def test_team_lookup_by_sport(self):
        for sport, code, name in iter_team_rows():
            db.session.add(Team(sport=sport, code=code, name=name))
        db.session.commit()
        _team_names_for_sport.cache_clear()

        self.assertEqual(get_team_name('GER', sport='football'), 'Germany')
        self.assertEqual(get_team_name('LAT', sport='hockey'), 'Latvia')
        self.assertEqual(get_team_name('LAT', sport='football'), 'LAT')
        self.assertEqual(get_team_name('TBD', sport='hockey'), 'TBD')

    def test_get_next_game_returns_none_without_schedule(self):
        self.assertIsNone(get_next_game())

    def test_get_next_game_returns_next_upcoming_game(self):
        past_game = Game(id=1, team_a='AUT', team_b='LAT',
                         starts_at=utcnow() - timedelta(days=1))
        next_game = Game(id=2, team_a='CAN', team_b='USA',
                         starts_at=utcnow() + timedelta(hours=1))
        later_game = Game(id=3, team_a='FIN', team_b='SWE',
                          starts_at=utcnow() + timedelta(days=1))
        db.session.add_all([past_game, next_game, later_game])
        db.session.commit()

        self.assertEqual(get_next_game(), next_game.id)

    def test_get_next_game_returns_last_game_after_tournament(self):
        first_game = Game(id=1, team_a='AUT', team_b='LAT',
                          starts_at=utcnow() - timedelta(days=2))
        last_game = Game(id=2, team_a='CAN', team_b='USA',
                         starts_at=utcnow() - timedelta(days=1))
        db.session.add_all([first_game, last_game])
        db.session.commit()

        self.assertEqual(get_next_game(), last_game.id)


class AdminPageCase(TestCaseBase):
    def make_admin(self, username='admin'):
        user = self.make_user(username)
        user.is_admin = True
        db.session.commit()
        return user

    def test_anonymous_admin_page_forbidden(self):
        with app.test_client() as client:
            response = client.get('/admin')
        self.assertEqual(response.status_code, 403)

    def test_non_admin_forbidden(self):
        user = self.make_user('player')
        with app.test_client() as client:
            self.login(client, user)
            response = client.get('/admin')
        self.assertEqual(response.status_code, 403)

    def test_admin_page_renders_for_admin(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.get('/admin')
        self.assertEqual(response.status_code, 200)
        body = response.data.decode('utf-8')
        self.assertIn('admin-page', body)
        self.assertIn('Admin Panel', body)

    def test_admin_page_has_section_navigation(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.get('/admin')
        body = response.data.decode('utf-8')
        for section_id in (
            'admin-admins', 'admin-users', 'admin-schedule',
            'admin-results', 'admin-winner',
        ):
            self.assertIn(f'id="{section_id}"', body)
        self.assertIn('admin-nav-link', body)

    def test_admin_page_shows_current_admins_as_chips(self):
        admin = self.make_admin('chief')
        self.make_admin('helper')
        with app.test_client() as client:
            self.login(client, admin)
            response = client.get('/admin')
        body = response.data.decode('utf-8')
        self.assertIn('chip--admin', body)
        self.assertIn('chief', body)
        self.assertIn('helper', body)

    def test_admin_page_includes_csv_format_guides(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.get('/admin')
        body = response.data.decode('utf-8')
        self.assertIn('admin-format-guide', body)
        self.assertIn('team_a,team_b,stage,starts_at', body)
        self.assertIn('description,last_bet,bet_points', body)

    def test_admin_page_uses_color_cards(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            body = client.get('/admin').data.decode('utf-8')
        for color in ('primary', 'secondary', 'bright', 'accent'):
            self.assertIn(f'admin-card--{color}', body)

    def test_admin_page_renders_all_expected_form_fields(self):
        admin = self.make_admin()
        finished = Game(
            team_a='CAN', team_b='USA',
            starts_at=utcnow() - timedelta(hours=2),
            score_a=1, score_b=0, first_goal=1,
        )
        unfinished = Game(
            team_a='NED', team_b='POR',
            starts_at=utcnow() - timedelta(hours=1),
        )
        tbd = Game(
            team_a='TBD', team_b='TBD',
            starts_at=utcnow() + timedelta(days=1),
        )
        db.session.add_all([finished, unfinished, tbd])
        db.session.commit()

        with app.test_client() as client:
            self.login(client, admin)
            body = client.get('/admin').data.decode('utf-8')

        for field_name in (
            'upload_game_score-game_id',
            'upload_game_score-score_a',
            'upload_game_score-score_b',
            'upload_game_score-first_goal',
            'correct_game_score-game_id',
            'correct_game_score-score_a',
            'correct_game_score-score_b',
            'correct_game_score-first_goal',
            'add-users',
            'remove-users',
            'remove_user-users',
            'final_winner',
            'upload_game_schedule-csv_file',
            'upload_winner_bet_points-csv_file',
            'set_game-game_id',
            'set_game-team_a',
            'set_game-team_b',
        ):
            with self.subTest(field=field_name):
                self.assertIn(f'name="{field_name}"', body)

        for submit_name in (
            'upload_game_score-submit',
            'correct_game_score-submit',
            'add-submit',
            'remove-submit',
            'remove_user-submit',
            'submit',
            'upload_game_schedule-submit',
            'upload_winner_bet_points-submit',
            'set_game-submit',
        ):
            with self.subTest(submit=submit_name):
                self.assertIn(f'name="{submit_name}"', body)

    def test_admin_page_renders_nine_post_forms(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            body = client.get('/admin').data.decode('utf-8')
        self.assertEqual(body.count('method="post"'), 9)
        self.assertEqual(body.count('admin-card-form'), 9)

    def test_admin_score_forms_render_first_goal_radios(self):
        admin = self.make_admin()
        game = Game(
            team_a='CAN', team_b='USA',
            starts_at=utcnow() - timedelta(hours=1),
        )
        db.session.add(game)
        db.session.commit()
        with app.test_client() as client:
            self.login(client, admin)
            body = client.get('/admin').data.decode('utf-8')
        self.assertIn('name="upload_game_score-first_goal"', body)
        self.assertIn('name="correct_game_score-first_goal"', body)
        self.assertIn('type="radio"', body)
        self.assertIn('admin-match-pick', body)
        self.assertIn('admin-score-input', body)

    def test_admin_post_ignored_without_matching_submit_button(self):
        admin = self.make_admin()
        player = self.make_user('player')
        game = Game(
            team_a='CAN', team_b='USA',
            starts_at=utcnow() - timedelta(hours=1),
        )
        db.session.add(game)
        db.session.commit()
        with app.test_client() as client:
            self.login(client, admin)
            client.post('/admin', data={
                'upload_game_score-game_id': game.id,
                'upload_game_score-score_a': 2,
                'upload_game_score-score_b': 1,
                'upload_game_score-first_goal': 1,
            })
        db.session.refresh(game)
        db.session.refresh(player)
        self.assertIsNone(game.score_a)
        self.assertFalse(player.is_admin)

    def test_admin_add_form_ignored_without_submit_button(self):
        admin = self.make_admin()
        player = self.make_user('player')
        with app.test_client() as client:
            self.login(client, admin)
            client.post('/admin', data={'add-users': player.id})
        db.session.refresh(player)
        self.assertFalse(player.is_admin)

    def test_admin_csv_forms_render_file_inputs(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            body = client.get('/admin').data.decode('utf-8')
        self.assertIn('name="upload_game_schedule-csv_file"', body)
        self.assertIn('name="upload_winner_bet_points-csv_file"', body)
        self.assertGreaterEqual(body.count('type="file"'), 2)

    def test_admin_page_csv_forms_keep_upload_actions(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.get('/admin')
        body = response.data.decode('utf-8')
        self.assertIn('action="/upload_csv"', body)
        self.assertIn('action="/upload_winnerbet_csv"', body)
        self.assertIn('enctype="multipart/form-data"', body)

    def test_admin_page_section_headings_use_rules_style(self):
        admin = self.make_admin()
        with app.test_client() as client:
            self.login(client, admin)
            body = client.get('/admin').data.decode('utf-8')
        for heading in ('Game Results', 'Admins', 'Users', 'Tournament Winner Team', 'Game Schedule'):
            self.assertIn(f'<h4>{heading}</h4>', body)

    def test_add_admin_promotes_user(self):
        admin = self.make_admin()
        player = self.make_user('player')
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post('/admin', data={
                'add-users': player.id,
                'add-submit': 'Save',
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(player)
        self.assertTrue(player.is_admin)

    def test_remove_admin_revokes_user(self):
        admin = self.make_admin()
        other_admin = self.make_admin('other')
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post('/admin', data={
                'remove-users': other_admin.id,
                'remove-submit': 'Save',
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(other_admin)
        self.assertFalse(other_admin.is_admin)

    def test_hide_user_from_standings(self):
        admin = self.make_admin()
        player = self.make_user('player')
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post('/admin', data={
                'remove_user-users': player.id,
                'remove_user-submit': 'Save',
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(player)
        self.assertFalse(player.is_shown)

    def test_set_tbd_game_updates_teams(self):
        admin = self.make_admin()
        game = Game(team_a='TBD', team_b='TBD',
                    starts_at=utcnow() + timedelta(days=1))
        db.session.add(game)
        db.session.commit()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post('/admin', data={
                'set_game-game_id': game.id,
                'set_game-team_a': 'CAN',
                'set_game-team_b': 'USA',
                'set_game-submit': 'Set Game',
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(game)
        self.assertEqual(game.team_a, 'CAN')
        self.assertEqual(game.team_b, 'USA')

    def test_submit_game_score_saves_result(self):
        admin = self.make_admin()
        game = Game(team_a='CAN', team_b='USA',
                    starts_at=utcnow() - timedelta(hours=1))
        db.session.add(game)
        db.session.commit()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post('/admin', data={
                'upload_game_score-game_id': game.id,
                'upload_game_score-score_a': 2,
                'upload_game_score-score_b': 1,
                'upload_game_score-first_goal': 1,
                'upload_game_score-submit': 'Upload Result',
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(game)
        self.assertEqual(game.score_a, 2)
        self.assertEqual(game.score_b, 1)
        self.assertEqual(game.first_goal, 1)

    def test_correct_game_score_updates_result(self):
        admin = self.make_admin()
        game = Game(team_a='CAN', team_b='USA',
                    starts_at=utcnow() - timedelta(hours=1),
                    score_a=1, score_b=0, first_goal=1)
        db.session.add(game)
        db.session.commit()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post('/admin', data={
                'correct_game_score-game_id': game.id,
                'correct_game_score-score_a': 3,
                'correct_game_score-score_b': 2,
                'correct_game_score-first_goal': 2,
                'correct_game_score-submit': 'Upload Result',
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(game)
        self.assertEqual(game.score_a, 3)
        self.assertEqual(game.score_b, 2)
        self.assertEqual(game.first_goal, 2)

    def test_submit_winner_team_awards_points(self):
        admin = self.make_admin()
        player = self.make_user('player', overall_points=0, final_winner_points=0)
        player.final_winner = 'CAN'
        player.final_winner_timestamp = utcnow() - timedelta(hours=1)
        db.session.add(Game(team_a='CAN', team_b='USA',
                            starts_at=utcnow() + timedelta(days=1)))
        db.session.add(Winnerbet(description='Early',
                                 last_bet=utcnow() + timedelta(days=1),
                                 bet_points=12))
        db.session.commit()
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post('/admin', data={
                'final_winner': 'CAN',
                'submit': 'Submit',
            }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(player)
        self.assertEqual(player.final_winner_points, 12)
        self.assertEqual(player.overall_points, 12)

    def test_upload_game_schedule_csv(self):
        admin = self.make_admin()
        csv_content = (
            'team_a,team_b,stage,starts_at\n'
            'CAN,USA,Group,2026-07-01 15:00:00\n'
        ).encode('utf-8')
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post(
                '/upload_csv',
                data={
                    'upload_game_schedule-csv_file': (
                        io.BytesIO(csv_content), 'schedule.csv'),
                    'upload_game_schedule-submit': 'Upload',
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        game = Game.query.filter_by(team_a='CAN', team_b='USA').first()
        self.assertIsNotNone(game)
        self.assertEqual(game.stage, 'Group')

    def test_upload_winnerbet_csv(self):
        admin = self.make_admin()
        csv_content = (
            'description,last_bet,bet_points\n'
            'Final day,2026-08-01 12:00:00,15\n'
        ).encode('utf-8')
        with app.test_client() as client:
            self.login(client, admin)
            response = client.post(
                '/upload_winnerbet_csv',
                data={
                    'upload_winner_bet_points-csv_file': (
                        io.BytesIO(csv_content), 'winnerbet.csv'),
                    'upload_winner_bet_points-submit': 'Upload',
                },
                content_type='multipart/form-data',
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        row = Winnerbet.query.filter_by(description='Final day').first()
        self.assertIsNotNone(row)
        self.assertEqual(row.bet_points, 15)


class SecurityHookCase(unittest.TestCase):
    def test_distutils_strict_version_is_available(self):
        version_module = importlib.import_module('distutils.version')
        self.assertTrue(hasattr(version_module, 'StrictVersion'))

    def test_pre_push_hook_runs_tests_and_vulnerability_audit(self):
        hook_path = Path('.githooks/pre-push')
        self.assertTrue(hook_path.exists(), 'pre-push hook is missing')
        self.assertTrue(hook_path.is_file(), 'pre-push hook is not a file')
        self.assertTrue(hook_path.stat().st_mode & 0o111, 'pre-push hook is not executable')
        hook_text = hook_path.read_text(encoding='utf-8')
        self.assertIn('unittest tests', hook_text)
        self.assertIn('pip-audit', hook_text)
        self.assertIn('-r requirements.txt', hook_text)

    def test_hook_bootstrap_is_documented_and_configures_git(self):
        script_path = Path('scripts/setup-git-hooks.sh')
        readme_path = Path('README.md')
        self.assertTrue(script_path.exists(), 'bootstrap script is missing')
        self.assertTrue(readme_path.exists(), 'README is missing')
        script_text = script_path.read_text(encoding='utf-8')
        readme_text = readme_path.read_text(encoding='utf-8')
        self.assertIn('git config core.hooksPath .githooks', script_text)
        self.assertIn('scripts/setup-git-hooks.sh', readme_text)
        self.assertIn('.githooks/pre-push', readme_text)


class HomeChartsCase(TestCaseBase):
    def test_build_home_chart_data_with_games_and_bets(self):
        self.set_sport('football')
        leader = self.make_user('leader', is_shown=True, overall_points=20,
                                total_points=20, total_score=3, total_score_diff=2,
                                total_winner=4, total_first_goal=2, total_closed_bets=2)
        runner = self.make_user('runner', is_shown=True, overall_points=12,
                                total_points=12, total_score=2, total_score_diff=1,
                                total_winner=2, total_first_goal=1, total_closed_bets=2)
        hidden = self.make_user('hidden', is_shown=False, overall_points=99,
                                total_points=99, total_closed_bets=2)
        game1 = Game(team_a='GER', team_b='SCO', stage='Group', starts_at=utcnow(),
                     score_a=2, score_b=1, first_goal=1)
        game2 = Game(team_a='FRA', team_b='BEL', stage='Group',
                     starts_at=utcnow() + timedelta(days=2))
        db.session.add_all([game1, game2])
        db.session.flush()

        leader_bet1 = Bet(user_id=leader.id, game_id=game1.id, score_a=2, score_b=1,
                          first_goal=1, is_default_bet=False)
        leader_bet2 = Bet(user_id=leader.id, game_id=game2.id, score_a=1, score_b=1,
                          first_goal=1, is_default_bet=False)
        runner_bet1 = Bet(user_id=runner.id, game_id=game1.id, score_a=1, score_b=1,
                          first_goal=1, is_default_bet=False)
        apply_bet_scoring(leader_bet1, game1, 'football')
        apply_bet_scoring(runner_bet1, game1, 'football')
        db.session.add_all([leader_bet1, leader_bet2, runner_bet1])
        db.session.commit()

        client = app.test_client()
        self.login(client, runner)

        with app.test_request_context('/'):
            from flask_login import login_user
            login_user(runner)
            data = build_home_chart_data(runner)

        self.assertEqual(len(data['labels']), 1)
        self.assertGreaterEqual(len(data['points_race']['datasets']), 1)
        self.assertEqual(
            len(data['points_race']['datasets']),
            len(data['rank_over_time']['datasets']),
        )
        self.assertEqual(
            len(data['points_race']['datasets']),
            len(data['heatmap']['rows']),
        )
        self.assertEqual(len(data['heatmap']['rows']), 2)
        self.assertEqual(data['heatmap']['rows'][0]['username'], 'runner')
        self.assertEqual(data['heatmap']['rows'][1]['username'], 'leader')
        self.assertEqual(len(data['labels']), 1)

    def test_heatmap_shows_only_recent_games(self):
        self.set_sport('football')
        user = self.make_user('player', is_shown=True, overall_points=0, total_points=0,
                              total_closed_bets=0)
        games = []
        for index in range(15):
            games.append(Game(
                team_a='GER',
                team_b=f'T{index}',
                stage='Group',
                starts_at=utcnow() + timedelta(days=index),
                score_a=1,
                score_b=0,
                first_goal=1,
            ))
        db.session.add_all(games)
        db.session.commit()

        with app.test_request_context('/'):
            from flask_login import login_user
            login_user(user)
            data = build_home_chart_data(user)

        self.assertEqual(len(data['labels']), 12)
        self.assertEqual(data['labels'][0], 'GER-T3')
        self.assertEqual(data['labels'][-1], 'GER-T14')

    def test_charts_limit_users_to_top_ten_plus_current(self):
        self.set_sport('football')
        for index in range(11):
            self.make_user(
                f'topper{index}',
                is_shown=True,
                overall_points=100 - index,
                total_points=100 - index,
                total_closed_bets=1,
            )
        outsider = self.make_user(
            'outsider',
            is_shown=True,
            overall_points=1,
            total_points=1,
            total_closed_bets=1,
        )
        game = Game(team_a='GER', team_b='SCO', stage='Group', starts_at=utcnow(),
                    score_a=1, score_b=0, first_goal=1)
        db.session.add(game)
        db.session.commit()

        with app.test_request_context('/'):
            from flask_login import login_user
            login_user(outsider)
            data = build_home_chart_data(outsider)

        self.assertEqual(data['chart_top_users'], 10)
        self.assertEqual(len(data['points_race']['datasets']), 11)
        self.assertEqual(len(data['rank_over_time']['datasets']), 11)
        self.assertEqual(len(data['heatmap']['rows']), 11)
        self.assertEqual(data['heatmap']['rows'][0]['username'], 'outsider')
        usernames = {row['username'] for row in data['heatmap']['rows']}
        self.assertIn('outsider', usernames)
        self.assertNotIn('topper10', usernames)

    def test_closed_games_include_first_goal_zero(self):
        self.set_sport('football')
        user = self.make_user('player', is_shown=True, overall_points=0, total_points=0,
                              total_closed_bets=0)
        older = Game(team_a='GER', team_b='SCO', stage='Group',
                     starts_at=utcnow() - timedelta(days=2),
                     score_a=0, score_b=0, first_goal=0)
        latest = Game(team_a='FRA', team_b='BEL', stage='Group',
                      starts_at=utcnow() - timedelta(days=1),
                      score_a=1, score_b=0, first_goal=1)
        db.session.add_all([older, latest])
        db.session.commit()

        with app.test_request_context('/'):
            from flask_login import login_user
            login_user(user)
            data = build_home_chart_data(user)

        self.assertEqual(len(data['labels']), 2)
        self.assertEqual(data['labels'][-1], 'FRA-BEL')

    def test_rank_over_time_uses_full_season_not_recent_window(self):
        self.set_sport('football')
        early = self.make_user('early', is_shown=True, overall_points=0, total_points=0,
                               total_closed_bets=0)
        late = self.make_user('late', is_shown=True, overall_points=0, total_points=0,
                              total_closed_bets=0)
        games = []
        for index in range(15):
            games.append(Game(
                team_a='GER',
                team_b=f'T{index}',
                stage='Group',
                starts_at=utcnow() + timedelta(days=index),
                score_a=1,
                score_b=0,
                first_goal=1,
            ))
        db.session.add_all(games)
        db.session.flush()

        bets = []
        for index, game in enumerate(games):
            if index < 3:
                bets.append(Bet(
                    user_id=late.id,
                    game_id=game.id,
                    score_a=1,
                    score_b=0,
                    first_goal=1,
                    points=10,
                    winner_correct=True,
                    score_diff_correct=True,
                    score_correct=True,
                    is_default_bet=False,
                ))
            else:
                bets.append(Bet(
                    user_id=early.id,
                    game_id=game.id,
                    score_a=1,
                    score_b=0,
                    first_goal=1,
                    points=5,
                    winner_correct=True,
                    score_diff_correct=False,
                    score_correct=False,
                    is_default_bet=False,
                ))
        db.session.add_all(bets)
        db.session.commit()

        with app.test_request_context('/'):
            from flask_login import login_user
            login_user(early)
            data = build_home_chart_data(early)

        late_ranks = next(
            dataset['data']
            for dataset in data['rank_over_time']['datasets']
            if dataset['username'] == 'late'
        )
        self.assertEqual(len(late_ranks), 12)
        self.assertEqual(late_ranks[0], 1)

    def test_index_page_renders_home_charts(self):
        self.set_sport('football')
        user = self.make_user('viewer', is_shown=True, overall_points=5, total_points=5,
                              total_closed_bets=0, default_score_a=1, default_score_b=0,
                              default_first_goal=1, final_winner='GER')
        game = Game(team_a='GER', team_b='SCO', stage='Group', starts_at=utcnow(),
                    score_a=1, score_b=0, first_goal=1)
        db.session.add(game)
        db.session.commit()

        client = app.test_client()
        self.login(client, user)
        response = client.get('/index')
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('chart-points-race', body)
        self.assertIn('chart-rank-over-time', body)
        self.assertIn('HOME_CHART_DATA', body)
        self.assertIn('home-heatmap-panel', body)
        self.assertIn('Top 10 plus you', body)
        self.assertIn('Chat', body)


if __name__ == '__main__':
    unittest.main(verbosity=2)
