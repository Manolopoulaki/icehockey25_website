"""Bet grading and point calculation per competition rules (rules.html)."""

POINT_VALUES = {
    'hockey': {
        'first_goal': 1,
        'outcome': 3,
        'score_diff': 1,
        'exact_score': 3,
    },
    'football': {
        'first_goal': 1,
        'outcome': 2,
        'score_diff': 1,
        'exact_score': 3,
    },
}


def point_values(sport):
    return POINT_VALUES[sport]


def _outcome_correct(bet_score_a, bet_score_b, game_score_a, game_score_b):
    return (
        (bet_score_a > bet_score_b and game_score_a > game_score_b)
        or (bet_score_b > bet_score_a and game_score_b > game_score_a)
        or (bet_score_b == bet_score_a and game_score_b == game_score_a)
    )


def grade_bet(bet, game):
    """Set correctness flags on bet from final game result."""
    bet.first_goal_correct = bet.first_goal == int(game.first_goal)
    bet.score_correct = bet.score_a == game.score_a and bet.score_b == game.score_b
    bet.winner_correct = _outcome_correct(
        bet.score_a, bet.score_b, game.score_a, game.score_b
    )
    bet.score_diff_correct = (
        bet.winner_correct
        and abs(bet.score_a - bet.score_b) == abs(game.score_a - game.score_b)
    )


def compute_bet_points(sport, first_goal_correct, winner_correct,
                       score_diff_correct, score_correct):
    """Return total points for one graded bet."""
    values = point_values(sport)
    total = 0
    if first_goal_correct:
        total += values['first_goal']
    if winner_correct:
        total += values['outcome']
    if score_diff_correct:
        total += values['score_diff']
    if score_correct:
        total += values['exact_score']
    return total


def apply_bet_scoring(bet, game, sport):
    grade_bet(bet, game)
    bet.points = compute_bet_points(
        sport,
        bet.first_goal_correct,
        bet.winner_correct,
        bet.score_diff_correct,
        bet.score_correct,
    )
