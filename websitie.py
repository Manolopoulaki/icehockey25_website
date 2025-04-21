from app import app, db
from app.models import User, Post, Game, Bet, Winnerbet

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Post': Post, 'Game':Game, 'Bet':Bet, 'Winnerbet':Winnerbet}
