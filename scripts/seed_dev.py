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
    {'username': 'linda', 'email': 'linda@example.com', 'about_me': 'Late-night bettor.', 'is_shown': False},
]

FINISHED_GAMES = [
    {'team_a': 'GER', 'team_b': 'SCO', 'stage': 'Group A', 'days_ago': 5,
     'score_a': 2, 'score_b': 1, 'first_goal': 1},
    {'team_a': 'FRA', 'team_b': 'BEL', 'stage': 'Group B', 'days_ago': 4,
     'score_a': 1, 'score_b': 1, 'first_goal': 1},
    {'team_a': 'ESP', 'team_b': 'ITA', 'stage': 'Group C', 'days_ago': 3,
     'score_a': 3, 'score_b': 0, 'first_goal': 1},
    {'team_a': 'ENG', 'team_b': 'WAL', 'stage': 'Group D', 'days_ago': 2,
     'score_a': 2, 'score_b': 0, 'first_goal': 1},
    {'team_a': 'BRA', 'team_b': 'ARG', 'stage': 'Group E', 'days_ago': 1,
     'score_a': 1, 'score_b': 2, 'first_goal': 2},
]

UPCOMING_GAMES = [
    {'team_a': 'NED', 'team_b': 'POR', 'stage': 'Quarter Final', 'days_ahead': 2},
    {'team_a': 'CAN', 'team_b': 'USA', 'stage': 'Quarter Final', 'days_ahead': 3},
    {'team_a': 'TBD', 'team_b': 'TBD', 'stage': 'Semi Final', 'days_ahead': 7},
]

# (score_a, score_b, first_goal) per finished game index for each user key.
PREDICTIONS = {
    'admin':  [(2, 1, 1), (1, 1, 1), (3, 0, 1), (2, 0, 1), (1, 2, 2)],
    'alice':   [(2, 1, 1), (2, 0, 1), (3, 0, 1), (1, 0, 1), (0, 2, 2)],
    'bob':     [(1, 0, 1), (1, 1, 2), (2, 1, 1), (2, 0, 1), (1, 1, 1)],
    'hektor':  [(3, 1, 1), (0, 0, 0), (3, 0, 2), (2, 0, 1), (1, 3, 1)],
    'maria':   [(2, 1, 2), (1, 1, 1), (2, 0, 1), (3, 0, 1), (2, 1, 1)],
    'toms':    [(1, 1, 1), (1, 1, 1), (1, 1, 1), (1, 1, 1), (2, 2, 1)],
    'linda':   [(0, 1, 2), (2, 2, 1), (0, 1, 2), (0, 2, 2), (3, 0, 1)],
}

UPCOMING_PREDICTIONS = {
    'admin':  [(2, 1, 1), (1, 2, 2)],
    'alice':  [(1, 1, 1), (2, 2, 0)],
    'bob':    [(0, 2, 2), (3, 1, 1)],
    'hektor': [(2, 0, 1), (1, 3, 2)],
    'maria':  [(1, 0, 1), (0, 0, 0)],
    'toms':   [(2, 2, 1), (1, 1, 1)],
    'linda':  [(1, 2, 2), (2, 1, 1)],
}

WINNER_PICKS = {
    'admin': 'GER',
    'alice': 'ESP',
    'bob': 'FRA',
    'hektor': 'BRA',
    'maria': 'ENG',
    'toms': 'ARG',
}

CHAT_POSTS = [
    ('admin', 'Welcome everyone — good luck with your picks!'),
    ('alice', 'GER-SCO was a nail-biter.'),
    ('bob', 'Still backing France all the way.'),
    ('hektor', 'Who had first goal in ESP-ITA?'),
    ('maria', 'Quarter finals are going to be wild.'),
]


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


def recalculate_user_stats(sport):
    for user in User.query.all():
        bets = Bet.query.filter_by(user_id=user.id).all()
        user.total_score = sum(1 for b in bets if b.score_correct)
        user.total_score_diff = sum(1 for b in bets if b.score_diff_correct)
        user.total_winner = sum(1 for b in bets if b.winner_correct)
        user.total_first_goal = sum(1 for b in bets if b.first_goal_correct)
        user.total_points = sum(b.points or 0 for b in bets)
        user.total_closed_bets = sum(
            1 for b in bets if b.game and b.game.first_goal and b.game.first_goal > 0
        )
        user.overall_points = user.total_points + (user.final_winner_points or 0)


def seed():
    sport = app.config['SPORT']
    now = utcnow()

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
    if Game.query.filter(Game.score_a.isnot(None)).count() < len(FINISHED_GAMES):
        for spec in FINISHED_GAMES:
            existing = Game.query.filter_by(
                team_a=spec['team_a'],
                team_b=spec['team_b'],
                stage=spec['stage'],
            ).first()
            if existing:
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
    else:
        finished_games = Game.query.filter(Game.score_a.isnot(None)).order_by(
            Game.starts_at.asc()
        ).all()

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

    for username, user in users.items():
        picks = PREDICTIONS.get(username, [])
        for game, pick in zip(finished_games, picks):
            if Bet.query.filter_by(user_id=user.id, game_id=game.id).first():
                continue
            bet = Bet(
                user_id=user.id,
                game_id=game.id,
                score_a=pick[0],
                score_b=pick[1],
                first_goal=pick[2],
                timestamp=game.starts_at - timedelta(hours=2),
            )
            apply_bet_scoring(bet, game, sport)
            db.session.add(bet)

        upcoming_picks = UPCOMING_PREDICTIONS.get(username, [])
        for game, pick in zip(upcoming_games[:2], upcoming_picks):
            if Bet.query.filter_by(user_id=user.id, game_id=game.id).first():
                continue
            db.session.add(Bet(
                user_id=user.id,
                game_id=game.id,
                score_a=pick[0],
                score_b=pick[1],
                first_goal=pick[2],
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

    recalculate_user_stats(sport)
    db.session.commit()

    print('Dev database seeded successfully.')
    print(f'Sport: {sport}')
    print(f'Users: {User.query.count()} (password for new users: {DEV_PASSWORD})')
    print(f'Games: {Game.query.count()} ({len(finished_games)} finished, {len(upcoming_games)} upcoming/TBD)')
    print(f'Bets: {Bet.query.count()}')
    print(f'Winner tiers: {Winnerbet.query.count()}')
    print(f'Chat posts: {Post.query.count()}')
    print('Sample logins: admin, alice, bob, hektor, maria, toms (all password: cat)')


if __name__ == '__main__':
    with app.app_context():
        seed()
