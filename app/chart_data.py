"""Aggregate data for home-page analytics charts."""

from collections import defaultdict

from app import db
from app.models import Bet, Game, User

# Last N finished games shown on all home charts (line plots + heatmap).
HOME_RECENT_GAMES = 12
# Top N users by standings, plus the current user when not already included.
HOME_CHART_TOP_USERS = 10
# Matches finished-game checks elsewhere in the app (games.html, user.html).
CLOSED_FIRST_GOAL_VALUES = (0, 1, 2)


def _shown_users():
    return User.query.filter(User.is_shown.is_(True)).order_by(
        User.overall_points.desc(),
        User.total_score.desc(),
        User.total_score_diff.desc(),
        User.total_winner.desc(),
        User.total_first_goal.desc(),
    ).all()


def _closed_games():
    return (
        Game.query.filter(Game.first_goal.in_(CLOSED_FIRST_GOAL_VALUES))
        .order_by(Game.starts_at.asc(), Game.id.asc())
        .all()
    )


def _recent_closed_games(limit=HOME_RECENT_GAMES):
    games = _closed_games()
    if len(games) <= limit:
        return games, 0
    return games[-limit:], len(games) - limit


def _recent_labels(games, offset):
    return [_game_label(game, offset + index) for index, game in enumerate(games)]


def _tail(items, count):
    if not items or count <= 0:
        return []
    return items[-count:]


def _chart_users(current_user, users, limit=HOME_CHART_TOP_USERS):
    """Top users by standings plus the current user when not already included."""
    selected = list(users[:limit])
    selected_ids = {user.id for user in selected}
    if (
        current_user
        and current_user.is_authenticated
        and current_user.is_shown
        and current_user.id not in selected_ids
    ):
        for user in users:
            if user.id == current_user.id:
                selected.append(user)
                break
    return selected


def _chart_users_with_current_first(current_user, chart_users):
    if not current_user or not current_user.is_authenticated or not current_user.is_shown:
        return chart_users
    if not any(user.id == current_user.id for user in chart_users):
        return chart_users
    return [current_user] + [user for user in chart_users if user.id != current_user.id]


def _is_current_user(current_user, user):
    return (
        current_user
        and current_user.is_authenticated
        and user.id == current_user.id
    )


def _game_label(game, index):
    if game.team_a == 'TBD' or game.team_b == 'TBD':
        return f'G{index + 1}'
    return f'{game.team_a}-{game.team_b}'


def _bet_stats_map():
    rows = (
        db.session.query(
            Bet.user_id,
            Bet.game_id,
            Bet.points,
            Bet.score_correct,
            Bet.score_diff_correct,
            Bet.winner_correct,
            Bet.first_goal_correct,
        )
        .join(User)
        .filter(User.is_shown.is_(True))
        .all()
    )
    return {
        (user_id, game_id): {
            'points': points or 0,
            'score': int(bool(score_correct)),
            'score_diff': int(bool(score_diff_correct)),
            'winner': int(bool(winner_correct)),
            'first_goal': int(bool(first_goal_correct)),
        }
        for user_id, game_id, points, score_correct, score_diff_correct, winner_correct, first_goal_correct in rows
    }


def _rank_users_by_standings(running_stats):
    """Rank users using the same tie-breakers as the standings page."""
    ordered = sorted(
        running_stats.items(),
        key=lambda item: (
            -item[1][0],
            -item[1][1],
            -item[1][2],
            -item[1][3],
            -item[1][4],
        ),
    )
    ranks = {}
    rank = 0
    prev_stats = None
    for position, (user_id, stats) in enumerate(ordered, start=1):
        if stats != prev_stats:
            rank = position
            prev_stats = stats
        ranks[user_id] = rank
    return ranks


def _apply_bet_stats_to_running(running_stats, user_id, bet_stats):
    stats = running_stats[user_id]
    stats[0] += bet_stats.get('points', 0)
    stats[1] += bet_stats.get('score', 0)
    stats[2] += bet_stats.get('score_diff', 0)
    stats[3] += bet_stats.get('winner', 0)
    stats[4] += bet_stats.get('first_goal', 0)


def build_home_chart_data(current_user):
    users = _shown_users()
    games = _closed_games()
    recent_games, game_label_offset = _recent_closed_games()
    recent_count = len(recent_games)
    recent_labels = _recent_labels(recent_games, game_label_offset)
    bet_stats_map = _bet_stats_map()

    chart_users = _chart_users(current_user, users)
    chart_user_ids = {user.id for user in chart_users}

    points_race_datasets = []
    for user in chart_users:
        running = 0
        series = []
        for game in games:
            running += bet_stats_map.get((user.id, game.id), {}).get('points', 0)
            series.append(running)
        points_race_datasets.append({
            'username': user.username,
            'data': _tail(series, recent_count),
            'is_current_user': _is_current_user(current_user, user),
        })

    heatmap_users = _chart_users_with_current_first(current_user, chart_users)
    max_heatmap_points = 1
    heatmap_rows = []
    for user in heatmap_users:
        row_points = [
            bet_stats_map.get((user.id, game.id), {}).get('points', 0)
            for game in recent_games
        ]
        max_heatmap_points = max(max_heatmap_points, max(row_points, default=0))
        heatmap_rows.append({
            'username': user.username,
            'points': row_points,
            'is_current_user': _is_current_user(current_user, user),
        })

    running_stats = {user.id: [0, 0, 0, 0, 0] for user in users}
    rank_history = defaultdict(list)
    for game in games:
        for user in users:
            bet_stats = bet_stats_map.get((user.id, game.id))
            if bet_stats:
                _apply_bet_stats_to_running(running_stats, user.id, bet_stats)
        ranks = _rank_users_by_standings(running_stats)
        for user_id in chart_user_ids:
            rank_history[user_id].append(ranks[user_id])

    rank_over_time_datasets = []
    for user in chart_users:
        rank_over_time_datasets.append({
            'username': user.username,
            'data': _tail(rank_history[user.id], recent_count),
            'is_current_user': _is_current_user(current_user, user),
        })

    return {
        'chart_top_users': HOME_CHART_TOP_USERS,
        'labels': recent_labels,
        'points_race': {'datasets': points_race_datasets},
        'heatmap': {
            'rows': heatmap_rows,
            'max_points': max_heatmap_points,
        },
        'rank_over_time': {'datasets': rank_over_time_datasets},
    }
