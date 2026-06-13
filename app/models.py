from hashlib import md5
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from app import db, login, app
from flask_login import UserMixin
from time import time
import jwt
from sqlalchemy.types import TypeDecorator, DateTime


def utcnow():
    return datetime.now(timezone.utc)

class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

def _session_get(model, identity):
    getter = getattr(db.session, 'get', None)
    if getter is not None:
        return getter(model, identity)
    return model.query.get(identity)

@login.user_loader
def load_user(id):
    return _session_get(User, int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False)
    is_shown = db.Column(db.Boolean, default=True)
    about_me = db.Column(db.String(140))
    last_seen = db.Column(UTCDateTime(), default=utcnow)
    default_score_a = db.Column(db.Integer)
    default_score_b = db.Column(db.Integer)
    default_first_goal = db.Column(db.Integer)
    final_winner = db.Column(db.String(3))
    final_winner_timestamp = db.Column(UTCDateTime(), index=True, default=utcnow)
    final_winner_points = db.Column(db.Integer)
    total_score = db.Column(db.Integer)
    total_score_diff = db.Column(db.Integer)
    total_winner = db.Column(db.Integer)
    total_first_goal = db.Column(db.Integer)
    total_points = db.Column(db.Integer)
    total_closed_bets = db.Column(db.Integer)
    overall_points = db.Column(db.Integer)
    bets = db.relationship('Bet', backref='user', lazy='dynamic')
    posts = db.relationship('Post', backref='author', lazy='dynamic')

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
            digest, size)

    def get_reset_password_token(self, expires_in=600):
        token = jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            app.config['SECRET_KEY'], algorithm='HS256')
        return token.decode('utf-8') if isinstance(token, bytes) else token

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return _session_get(User, id)
        
class Team(db.Model):
    sport = db.Column(db.String(16), primary_key=True)
    code = db.Column(db.String(3), primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    name_lv = db.Column(db.String(64))

    def __repr__(self):
        return f'<Team {self.sport} {self.code} {self.name}>'


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_a = db.Column(db.String(3), index=True)
    team_b = db.Column(db.String(3), index=True)
    stage = db.Column(db.String(17), index=True)
    starts_at = db.Column(UTCDateTime(), index=True, default=utcnow)
    score_a = db.Column(db.Integer)
    score_b = db.Column(db.Integer)
    first_goal = db.Column(db.Integer)
    bets = db.relationship('Bet', backref='game', lazy='dynamic')
    
    def __repr__(self):
        return '<Game {}-{}>'.format(self.team_a, self.team_b)
        
class Bet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), index=True)
    timestamp = db.Column(UTCDateTime(), index=True, default=utcnow)
    score_a = db.Column(db.Integer)
    score_b = db.Column(db.Integer)
    first_goal = db.Column(db.Integer)
    is_default_bet = db.Column(db.Boolean, default=False)
    first_goal_correct = db.Column(db.Boolean)
    winner_correct = db.Column(db.Boolean)
    score_diff_correct = db.Column(db.Boolean)
    score_correct = db.Column(db.Boolean)
    points = db.Column(db.Integer)

    def __repr__(self):
        return '<Bet {} from user {} for game {}>'.format(self.id, self.user_id, self.game_id)

class Winnerbet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(50))
    last_bet = db.Column(UTCDateTime(), index=True, default=utcnow)
    bet_points = db.Column(db.Integer)

    def __repr__(self):
        return '<For {}, {} point, {}s>'.format(self.id, self.bet_points, self.last_bet)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140))
    timestamp = db.Column(UTCDateTime(), index=True, default=utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return '<Post {}>'.format(self.body)
