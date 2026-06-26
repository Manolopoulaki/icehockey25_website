#!/usr/bin/env python3
"""Populate the local dev database with sample users, games, bets, and scores.

Usage:
    source venv/bin/activate
    python scripts/seed_dev.py

All seeded users have password: cat
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import timedelta

from app import app, db
from app.chart_data import CLOSED_FIRST_GOAL_VALUES
from app.models import Bet, Game, Post, Team, User, Winnerbet, utcnow
from app.scoring import apply_bet_scoring
from app.team_data import iter_team_rows


DEV_PASSWORD = 'cat'

USERS = [
    {'username': 'alice', 'email': 'alice@example.com', 'about_me': 'Loves exact scores.'},
    {'username': 'bob', 'email': 'bob@example.com', 'about_me': 'Outcomes over everything.'},
    {'username': 'hektor', 'email': 'hektor@example.com', 'about_me': 'First-goal specialist.'},
    {'username': 'maria', 'email': 'maria@example.com', 'about_me': 'Group stage grinder.'},
    {'username': 'toms', 'email': 'toms@example.com', 'about_me': 'Underdog picker.'},
    {'username': 'carlos', 'email': 'carlos@example.com', 'about_me': 'Late runs only.'},
    {'username': 'diana', 'email': 'diana@example.com', 'about_me': 'Draw merchant.'},
    {'username': 'erik', 'email': 'erik@example.com', 'about_me': 'Upset hunter.'},
    {'username': 'fiona', 'email': 'fiona@example.com', 'about_me': 'Clean-sheet believer.'},
    {'username': 'george', 'email': 'george@example.com', 'about_me': 'High-scoring picks.'},
    {'username': 'hanna', 'email': 'hanna@example.com', 'about_me': 'Form table watcher.'},
    {'username': 'ivan', 'email': 'ivan@example.com', 'about_me': 'Default-bet tester.'},
    {'username': 'julia', 'email': 'julia@example.com', 'about_me': 'Knockout specialist.'},
    {'username': 'klaus', 'email': 'klaus@example.com', 'about_me': 'Long-shot lover.'},
    {'username': 'linda', 'email': 'linda@example.com', 'about_me': 'Hidden from standings.', 'is_shown': False},
]

# team_a, team_b, score_a, score_b, first_goal
FINISHED_MATCHUPS = [
    ('GER', 'SCO', 2, 1, 1),
    ('FRA', 'BEL', 1, 1, 1),
    ('ESP', 'ITA', 3, 0, 1),
    ('ENG', 'WAL', 2, 0, 1),
    ('BRA', 'ARG', 1, 2, 2),
    ('NED', 'POR', 2, 2, 1),
    ('MEX', 'USA', 1, 0, 1),
    ('JPN', 'KOR', 0, 0, 0),
    ('CRO', 'DEN', 2, 1, 2),
    ('SUI', 'AUT', 1, 3, 2),
    ('URU', 'COL', 0, 1, 2),
    ('POL', 'SWE', 3, 2, 1),
    ('SRB', 'WAL', 1, 1, 1),
    ('CAN', 'ECU', 2, 0, 1),
    ('MAR', 'EGY', 1, 2, 2),
    ('AUS', 'TUN', 4, 1, 1),
    ('IRN', 'KSA', 0, 2, 2),
    ('CZE', 'TUR', 2, 1, 1),
]

UPCOMING_GAMES = [
    {'team_a': 'NED', 'team_b': 'POR', 'stage': 'Quarter Final', 'days_ahead': 2},
    {'team_a': 'CAN', 'team_b': 'USA', 'stage': 'Quarter Final', 'days_ahead': 3},
    {'team_a': 'GER', 'team_b': 'FRA', 'stage': 'Semi Final', 'days_ahead': 6},
    {'team_a': 'TBD', 'team_b': 'TBD', 'stage': 'Final', 'days_ahead': 10},
]

WINNER_PICKS = {
    'admin': 'GER',
    'alice': 'ESP',
    'bob': 'FRA',
    'hektor': 'BRA',
    'maria': 'ENG',
    'toms': 'ARG',
    'carlos': 'MEX',
    'diana': 'NED',
    'erik': 'CRO',
    'fiona': 'POR',
    'george': 'GER',
    'hanna': 'ITA',
    'ivan': 'BEL',
    'julia': 'FRA',
    'klaus': 'URU',
}

CHAT_POSTS = [
    ('admin', 'Welcome everyone — good luck with your picks!'),
    ('alice', 'GER-SCO was a nail-biter.'),
    ('bob', 'Still backing France all the way.'),
    ('hektor', 'Who had first goal in ESP-ITA?'),
    ('maria', 'Quarter finals are going to be wild.'),
    ('carlos', 'The heatmap is looking spicy.'),
    ('diana', 'JPN-KOR was the draw nobody wanted.'),
]


def build_finished_game_specs():
    total = len(FINISHED_MATCHUPS)
    specs = []
    for index, (team_a, team_b, score_a, score_b, first_goal) in enumerate(FINISHED_MATCHUPS):
        specs.append({
            'team_a': team_a,
            'team_b': team_b,
            'stage': f'Group {chr(65 + (index % 8))}',
            'days_ago': total - index,
            'score_a': score_a,
            'score_b': score_b,
            'first_goal': first_goal,
        })
    return specs


def prediction_for_user_game(user_index, game_index, game):
    """Deterministic picks with a mix of correct and incorrect results."""
    patterns = [
        (game.score_a, game.score_b, game.first_goal),
        (game.score_a, game.score_b, 1 if game.first_goal != 1 else 2),
        (max(game.score_a, game.score_b), min(game.score_a, game.score_b), game.first_goal),
        (game.score_a + 1, game.score_b, game.first_goal),
        (game.score_a, game.score_b + 1, 2 if game.score_b >= game.score_a else 1),
        (1, 1, 1),
        (0, 0, 0),
        (2, 0, 1),
    ]
    pick = patterns[(user_index + game_index) % len(patterns)]
    return pick


def upcoming_prediction_for_user_game(user_index, game_index):
    patterns = [
        (2, 1, 1),
        (1, 1, 1),
        (0, 2, 2),
        (3, 1, 1),
        (1, 0, 1),
        (2, 2, 1),
    ]
    return patterns[(user_index + game_index) % len(patterns)]


def seed_teams():
    if Team.query.count():
        return
    for sport, code, name in iter_team_rows():
        db.session.add(Team(sport=sport, code=code, name=name))
    db.session.commit()


def get_or_create_user(username, email, **kwargs):
    user = User.query.filter_by(username=username).first()
    if user:
        return user
    user = User(
        username=username,
        email=email,
        final_winner_points=0,
        total_score=0,
        total_score_diff=0,
        total_winner=0,
        total_first_goal=0,
        total_points=0,
        total_closed_bets=0,
        overall_points=0,
        **kwargs,
    )
    user.set_password(DEV_PASSWORD)
    db.session.add(user)
    db.session.flush()
    if user.id == 1:
        user.is_admin = True
    return user


def recalculate_user_stats():
    for user in User.query.all():
        bets = Bet.query.filter_by(user_id=user.id).all()
        user.total_score = sum(1 for b in bets if b.score_correct)
        user.total_score_diff = sum(1 for b in bets if b.score_diff_correct)
        user.total_winner = sum(1 for b in bets if b.winner_correct)
        user.total_first_goal = sum(1 for b in bets if b.first_goal_correct)
        user.total_points = sum(b.points or 0 for b in bets)
        user.total_closed_bets = sum(
            1 for b in bets
            if b.game and b.game.first_goal in CLOSED_FIRST_GOAL_VALUES
        )
        user.overall_points = user.total_points + (user.final_winner_points or 0)


def seed():
    sport = app.config['SPORT']
    now = utcnow()
    finished_specs = build_finished_game_specs()

    seed_teams()

    admin = User.query.filter_by(username='admin').first()
    if admin is None:
        admin = get_or_create_user('admin', 'admin@example.com', is_admin=True)
    else:
        admin.is_admin = True

    users = {'admin': admin}
    for spec in USERS:
        user = get_or_create_user(
            spec['username'],
            spec['email'],
            about_me=spec.get('about_me'),
            is_shown=spec.get('is_shown', True),
        )
        users[spec['username']] = user

    admin.default_score_a = 1
    admin.default_score_b = 0
    admin.default_first_goal = 1
    alice = users['alice']
    alice.default_score_a = 2
    alice.default_score_b = 1
    alice.default_first_goal = 1

    if not Winnerbet.query.count():
        db.session.add_all([
            Winnerbet(description='Early bird', last_bet=now + timedelta(days=14), bet_points=15),
            Winnerbet(description='Group stage end', last_bet=now + timedelta(days=30), bet_points=10),
            Winnerbet(description='Knockout start', last_bet=now + timedelta(days=45), bet_points=5),
        ])

    finished_games = []
    for spec in finished_specs:
        existing = Game.query.filter_by(
            team_a=spec['team_a'],
            team_b=spec['team_b'],
            stage=spec['stage'],
        ).first()
        if existing:
            existing.starts_at = now - timedelta(days=spec['days_ago'])
            existing.score_a = spec['score_a']
            existing.score_b = spec['score_b']
            existing.first_goal = spec['first_goal']
            finished_games.append(existing)
            continue
        game = Game(
            team_a=spec['team_a'],
            team_b=spec['team_b'],
            stage=spec['stage'],
            starts_at=now - timedelta(days=spec['days_ago']),
            score_a=spec['score_a'],
            score_b=spec['score_b'],
            first_goal=spec['first_goal'],
        )
        db.session.add(game)
        finished_games.append(game)

    finished_games.sort(key=lambda game: game.starts_at)

    upcoming_games = []
    for spec in UPCOMING_GAMES:
        existing = Game.query.filter_by(
            team_a=spec['team_a'],
            team_b=spec['team_b'],
            stage=spec['stage'],
        ).first()
        if existing:
            upcoming_games.append(existing)
            continue
        game = Game(
            team_a=spec['team_a'],
            team_b=spec['team_b'],
            stage=spec['stage'],
            starts_at=now + timedelta(days=spec['days_ahead']),
        )
        db.session.add(game)
        upcoming_games.append(game)

    db.session.flush()

    user_items = list(users.items())
    for user_index, (username, user) in enumerate(user_items):
        for game_index, game in enumerate(finished_games):
            if Bet.query.filter_by(user_id=user.id, game_id=game.id).first():
                continue
            score_a, score_b, first_goal = prediction_for_user_game(
                user_index, game_index, game
            )
            bet = Bet(
                user_id=user.id,
                game_id=game.id,
                score_a=score_a,
                score_b=score_b,
                first_goal=first_goal,
                timestamp=game.starts_at - timedelta(hours=2),
            )
            apply_bet_scoring(bet, game, sport)
            db.session.add(bet)

        for game_index, game in enumerate(upcoming_games[:3]):
            if Bet.query.filter_by(user_id=user.id, game_id=game.id).first():
                continue
            score_a, score_b, first_goal = upcoming_prediction_for_user_game(
                user_index, game_index
            )
            db.session.add(Bet(
                user_id=user.id,
                game_id=game.id,
                score_a=score_a,
                score_b=score_b,
                first_goal=first_goal,
                timestamp=now - timedelta(hours=1),
            ))

        winner = WINNER_PICKS.get(username)
        if winner and not user.final_winner:
            user.final_winner = winner
            user.final_winner_timestamp = now - timedelta(days=3)

    for username, body in CHAT_POSTS:
        user = users.get(username) or admin
        if not Post.query.filter_by(user_id=user.id, body=body).first():
            db.session.add(Post(body=body, user_id=user.id, timestamp=now - timedelta(hours=2)))

    recalculate_user_stats()
    db.session.commit()

    shown_users = User.query.filter_by(is_shown=True).count()
    closed_games = Game.query.filter(Game.first_goal.in_(CLOSED_FIRST_GOAL_VALUES)).count()
    print('Dev database seeded successfully.')
    print(f'Sport: {sport}')
    print(f'Users: {User.query.count()} ({shown_users} shown, password: {DEV_PASSWORD})')
    print(f'Games: {Game.query.count()} ({closed_games} finished, {len(upcoming_games)} upcoming/TBD)')
    print(f'Bets: {Bet.query.count()}')
    print(f'Winner tiers: {Winnerbet.query.count()}')
    print(f'Chat posts: {Post.query.count()}')
    print('Sample logins: admin, alice, bob, maria, toms, carlos, diana (all password: cat)')


if __name__ == '__main__':
    with app.app_context():
        seed()
