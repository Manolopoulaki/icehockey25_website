from functools import lru_cache

from flask import g, has_request_context

from app import app
from app.models import Team


@lru_cache(maxsize=4)
def _team_names_for_sport(sport):
    teams = Team.query.filter_by(sport=sport).all()
    return {team.code: team.name for team in teams}


def get_team_name(code, sport=None):
    if not code or code == 'TBD':
        return code or 'TBD'
    if sport is None:
        if has_request_context() and getattr(g, 'sport', None):
            sport = g.sport
        else:
            sport = app.config.get('SPORT', 'football')
    return _team_names_for_sport(sport).get(code, code)


def team_name_filter(code):
    return get_team_name(code)
