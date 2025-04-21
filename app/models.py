from hashlib import md5
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from app import db, login, app
from flask_login import UserMixin
from time import time
import jwt

@login.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    name = db.Column(db.String(64), index=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    verified = db.Column(db.Boolean, default=False)
    about_me = db.Column(db.String(140))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    default_score_a = db.Column(db.Integer)
    default_score_b = db.Column(db.Integer)
    default_first_goal = db.Column(db.Integer)
    final_winner = db.Column(db.String(3))
    final_winner_timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
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
        return 'https://www.gravatar.com/avatar/{}?d=wavatar&s={}'.format(
            digest, size)

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')
            
    def get_own_posts(self):
        return Post.query.join(
            User, (User.id == Post.user_id)).filter(
                User.id == self.id).order_by(
                    Post.timestamp.desc())
                    
#    def get_number_of_bets(self):
#        return Bet.query.join(
#            User, (User.id == Bet.user_id)).filter(
#                User.id == self.id).count()  
                
#    def get_total_points(self):
#        return Bet.query.join(
#            User, (User.id == Bet.user_id)).filter(
#                User.id == self.id).sum(Bet.points)                            

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)
        
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_a = db.Column(db.String(3), index=True)
    team_b = db.Column(db.String(3), index=True)
    stage = db.Column(db.String(17), index=True)
    starts_at = db.Column(db.DateTime, index=True, default=datetime.utcnow)
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
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
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
    last_bet = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    bet_points = db.Column(db.Integer)

    def __repr__(self):
        return '<For {}, {} point, {}s>'.format(self.id, self.bet_points, self.last_bet)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return '<Post {}>'.format(self.body)
