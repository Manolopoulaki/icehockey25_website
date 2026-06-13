from datetime import datetime, timedelta
from pathlib import Path
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
    league_accuracy_averages,
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


class TestCaseBase(unittest.TestCase):
    def setUp(self):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()
        self._original_sport = app.config['SPORT']

    def tearDown(self):
        app.config['SPORT'] = self._original_sport
        db.session.remove()
        db.drop_all()
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


class LeagueStatsCase(TestCaseBase):
    def test_league_accuracy_averages(self):
        u1 = self.make_user('a', is_shown=True, total_first_goal=2,
                            total_winner=4, total_score_diff=3, total_score=1,
                            total_closed_bets=10)
        u2 = self.make_user('b', is_shown=True, total_first_goal=0,
                            total_winner=2, total_score_diff=1, total_score=1,
                            total_closed_bets=10)
        self.make_user('hidden', is_shown=False, total_first_goal=10,
                       total_winner=10, total_score_diff=10, total_score=10,
                       total_closed_bets=10)
        db.session.commit()

        averages = league_accuracy_averages()
        self.assertEqual(averages['first_goal'], 10)
        self.assertEqual(averages['outcome'], 30)
        self.assertEqual(averages['score_diff'], 20)
        self.assertEqual(averages['score'], 10)

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
