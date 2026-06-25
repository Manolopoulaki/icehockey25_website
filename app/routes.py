from pathlib import Path
from flask import render_template, flash, redirect, request, url_for, g, session, abort, jsonify, make_response
from app import app, db
from app.forms import AdminsForm, LoginForm, RegistrationForm, PostForm, ResetPasswordRequestForm, ResetPasswordForm, EditProfileForm, PlaceBetForm, PlaceWinnerForm, UploadResultsForm, SetGame, UploadCSVForm, first_goal_choices, validate_bet_scores
from flask_login import current_user, login_user, logout_user, login_required
from app.models import User, Post, Game, Bet, Winnerbet, utcnow
from app.email import send_password_reset_email
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func, case
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.functions import coalesce
from flask_babel import get_locale
from flask_babel import _
from functools import wraps
import csv
from io import TextIOWrapper
from urllib.parse import urlsplit
from app.teams import get_team_name
from app.scoring import apply_bet_scoring

def winner_team_choices():
    teams = Game.query.filter(Game.team_a != 'TBD').with_entities(Game.team_b.label('team')).union(
        Game.query.filter(Game.team_b != 'TBD').with_entities(Game.team_a.label('team'))
    ).distinct().all()
    choices = [(g.team, get_team_name(g.team)) for g in teams]
    return sorted(choices, key=lambda choice: choice[1])

def get_user_stats(username):
    ranked_users_cte = db.session.query(
        func.rank().over(order_by=(
            User.overall_points.desc(),
            User.total_score.desc(),
            User.total_score_diff.desc(),
            User.total_winner.desc(),
            User.total_first_goal.desc(),
        )).label('ranking'),
        User.username,
        coalesce(User.total_score, 0).label('total_score'),
        coalesce(User.total_score_diff, 0).label('total_score_diff'),
        coalesce(User.total_winner, 0).label('total_winner'),
        coalesce(User.total_first_goal, 0).label('total_first_goal'),
        coalesce(User.total_points, 0).label('total_points'),
        coalesce(User.total_closed_bets, 0).label('total_closed_bets'),
        coalesce(User.overall_points, 0).label('overall_points'),
    ).cte(name='ranked_users')
    return db.session.query(ranked_users_cte).filter(
        ranked_users_cte.c.username == username
    ).first()

def winner_bet_points_for(user):
    if not user.final_winner_timestamp:
        return 0
    for tier in Winnerbet.query.order_by(Winnerbet.last_bet.asc()).all():
        if user.final_winner_timestamp <= tier.last_bet:
            return tier.bet_points
    return 0

def _user_bets_for_profile(profile_user):
    bets = profile_user.bets.order_by(Bet.game_id.asc()).join(Game).add_columns(
        Game.id,
        Game.team_a,
        Game.team_b,
        Game.starts_at,
        Bet.score_a.label('bet_score_a'),
        Bet.score_b.label('bet_score_b'),
        Bet.first_goal.label('bet_first_goal'),
        Game.score_a,
        Game.score_b,
        Game.first_goal,
        Bet.first_goal_correct,
        Bet.winner_correct,
        Bet.score_diff_correct,
        Bet.score_correct,
        Bet.points,
        Bet.is_default_bet,
    )
    if profile_user == current_user:
        return bets
    return bets.filter(Game.starts_at < utcnow())

def _build_own_profile_forms(profile_form=None):
    if profile_form is None:
        profile_form = EditProfileForm(current_user.username)
        profile_form.username.data = current_user.username
        profile_form.about_me.data = current_user.about_me
    default_form = PlaceBetForm()
    default_form.first_goal.choices = first_goal_choices(generic=True)
    if current_user.default_score_a is not None:
        default_form.score_a.data = current_user.default_score_a
        default_form.score_b.data = current_user.default_score_b
        default_form.first_goal.data = current_user.default_first_goal
    winner_form = PlaceWinnerForm()
    winner_form.final_winner.choices = winner_team_choices()
    if current_user.final_winner:
        winner_form.final_winner.data = current_user.final_winner
    return profile_form, default_form, winner_form, Winnerbet.query.all()

def everyone_accuracy_averages():
    row = db.session.query(
        func.coalesce(func.sum(User.total_first_goal), 0).label('first_goal'),
        func.coalesce(func.sum(User.total_winner), 0).label('outcome'),
        func.coalesce(func.sum(User.total_score_diff), 0).label('score_diff'),
        func.coalesce(func.sum(User.total_score), 0).label('score'),
        func.coalesce(func.sum(User.total_closed_bets), 0).label('closed'),
    ).filter(User.is_shown.is_(True)).first()
    if not row or not row.closed:
        return None
    return {
        'first_goal': int(round(row.first_goal * 100 / row.closed)),
        'outcome': int(round(row.outcome * 100 / row.closed)),
        'score_diff': int(round(row.score_diff * 100 / row.closed)),
        'score': int(round(row.score * 100 / row.closed)),
    }

def _render_user_profile(profile_user, setup=None, profile_form=None):
    profile_form_out = default_form = winner_form = winner_bet = None
    if profile_user == current_user:
        profile_form_out, default_form, winner_form, winner_bet = _build_own_profile_forms(profile_form)
    return render_template(
        'user.html',
        title=_('Profile'),
        sport=g.sport,
        user=profile_user,
        bets=_user_bets_for_profile(profile_user),
        user_stats=get_user_stats(profile_user.username),
        winner_bet_points=winner_bet_points_for(profile_user) if profile_user == current_user else 0,
        everyone_avg=everyone_accuracy_averages(),
        game_id=get_next_game(),
        setup=setup,
        profile_form=profile_form_out,
        default_form=default_form,
        winner_form=winner_form,
        winner_bet=winner_bet,
    )

@app.route('/manifest.webmanifest')
def web_manifest():
    icon_192 = url_for('static', filename='icons/pwa-192.png', _external=True)
    icon_512 = url_for('static', filename='icons/pwa-512.png', _external=True)
    return jsonify({
        'id': '/',
        'name': 'Sport Predictions',
        'short_name': 'Predictions',
        'description': 'Tournament predictions, standings, and game bets.',
        'start_url': url_for('login', _external=True),
        'scope': '/',
        'display': 'standalone',
        'display_override': ['standalone', 'minimal-ui'],
        'prefer_related_applications': False,
        'background_color': '#ffffff',
        'theme_color': '#32A685',
        'icons': [
            {'src': icon_192, 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': icon_512, 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
        ],
    }), 200, {'Content-Type': 'application/manifest+json; charset=utf-8', 'Cache-Control': 'no-cache'}

@app.route('/sw.js')
def service_worker():
    content = Path(app.static_folder, 'sw.js').read_text(encoding='utf-8')
    response = make_response(content)
    response.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    response.headers['Cache-Control'] = 'no-cache'
    return response

@app.before_request
def before_request():
    g.sport = app.config['SPORT']
    g.locale = str(get_locale())
    if current_user.is_authenticated:
        current_user.last_seen = utcnow()
        db.session.commit()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function    
        
def get_next_game():
    next_game = Game.query.filter(Game.starts_at > utcnow()).order_by(Game.starts_at.asc(), Game.id.asc()).first()
    if next_game is not None:
        return next_game.id

    last_game = Game.query.order_by(Game.starts_at.desc(), Game.id.desc()).first()
    return last_game.id if last_game is not None else None

def _submitted(form):
    return request.method == 'POST' and form.submit.name in request.form
        
@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():

    # chat form
    form = PostForm()
    if form.validate_on_submit():
        post = Post(body=form.post.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Your post is now live!')
        return redirect(url_for('index'))
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(
        page=page, per_page=app.config['POSTS_PER_PAGE'], error_out=False)#current_user.get_own_posts().all()
    next_url = url_for('index', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('index', page=posts.prev_num) \
        if posts.has_prev else None
    
    # leaders
    leader_first_goals = User.query.order_by(
        User.total_first_goal.desc(),
        User.total_points.desc(),
        User.total_score.desc(),
        User.total_score_diff.desc(),
        User.total_winner.desc()
    ).first()
    leader_points = User.query.order_by(
        User.total_points.desc(),
        User.total_score.desc(),
        User.total_score_diff.desc(),
        User.total_winner.desc(),
        User.total_first_goal.desc()
    ).first()
    leader_outcomes = User.query.order_by(
        User.total_winner.desc(),
        User.total_points.desc(),
        User.total_score.desc(),
        User.total_score_diff.desc(),
        User.total_first_goal.desc()
    ).first()
    leader_correct_scores = User.query.order_by(
        User.total_score.desc(),
        User.total_points.desc(),
        User.total_score_diff.desc(),
        User.total_winner.desc(),
        User.total_first_goal.desc()
    ).first()
    leaders_dict = {'leader_first_goals':leader_first_goals,
                    'leader_points':leader_points,
                    'leader_outcomes':leader_outcomes,
                    'leader_correct_scores':leader_correct_scores}

    return render_template("index.html", title=_('Home'), sport=g.sport, form=form, posts=posts.items,
    			    next_url=next_url, prev_url=prev_url, leaders=leaders_dict, game_id=get_next_game())

@app.route('/rules', methods=['GET', 'POST'])
@login_required
def rules():
    winner_bet = Winnerbet.query.all()
    return render_template("rules.html", title=_('Rules'), winner_bet=winner_bet, sport=g.sport, game_id=get_next_game())
    
@app.route('/standings', methods=['GET', 'POST'])
@login_required
def standings():
    # results = User.query.filter(User.is_shown==True).with_entities(func.rank().over(order_by=(User.overall_points.desc(), User.total_score.desc(), User.total_score_diff.desc(), User.total_winner.desc(), User.total_first_goal.desc())).label('ranking')).order_by('ranking').add_columns(User.username, User.overall_points, User.final_winner_points, User.total_score, User.total_score_diff, User.total_winner, User.total_first_goal, User.total_points, User.total_closed_bets).all()
    ranked_users_cte = db.session.query(func.rank().over(order_by=(User.overall_points.desc(), User.total_score.desc(), User.total_score_diff.desc(), User.total_winner.desc(), User.total_first_goal.desc())).label('ranking'), User.id, User.username, User.is_shown, User.overall_points, User.final_winner_points, User.total_score, User.total_score_diff, User.total_winner, User.total_first_goal, User.total_points, User.total_closed_bets).cte(name='ranked_users')
    results = db.session.query(ranked_users_cte).filter(ranked_users_cte.c.is_shown == True).order_by(ranked_users_cte.c.ranking).all()
    return render_template("standings.html", title=_('Standings'), sport=g.sport, results=results, game_id=get_next_game())
    
@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    games = Game.query.order_by(Game.id.asc()).all()
    return render_template("schedule.html", title=_('Schedule'), sport=g.sport, games=games, game_id=get_next_game())
    
@app.route('/place_predictions', methods=['GET', 'POST'])
@login_required
def place_predictions():
    current_time = utcnow()
    games = Game.query.filter(and_(Game.team_a != 'TBD', Game.team_b != 'TBD', Game.starts_at > current_time)).order_by(Game.starts_at.asc(), Game.id.asc()).all()
    forms = {}
    
    for game in games:
        form = PlaceBetForm()
        forms[game.id] = form
        form.first_goal.choices = first_goal_choices(game.team_a, game.team_b)
        existing_bet = current_user.bets.filter(and_(Bet.game_id==game.id, Bet.is_default_bet==False)).first()
        if existing_bet:
            form.score_a.data = existing_bet.score_a
            form.score_b.data = existing_bet.score_b
            form.first_goal.data = existing_bet.first_goal

    if request.method == 'POST':
        saved_count = 0
        for game in games:
            score_a_raw = request.form.get(f'score_a_{game.id}', '').strip()
            score_b_raw = request.form.get(f'score_b_{game.id}', '').strip()
            first_goal_raw = request.form.get(f'first_goal_{game.id}')
            if score_a_raw == '' or score_b_raw == '' or first_goal_raw is None:
                continue
            try:
                score_a = int(score_a_raw)
                score_b = int(score_b_raw)
                first_goal = int(first_goal_raw)
            except (ValueError, TypeError):
                flash(_('Invalid input for game %(game)s.', game=game.id), 'danger')
                continue
            if game.starts_at < current_time:
                flash(_('This game (%(gamea)s vs %(gameb)s) has already started.', gamea=game.team_a, gameb=game.team_b), 'danger')
                continue
            bet_error = validate_bet_scores(score_a, score_b, first_goal, g.sport)
            if bet_error:
                flash(_(bet_error), 'danger')
                continue
            current_user.bets.filter_by(game_id=game.id).delete()
            bet = Bet(game_id=game.id, score_a=score_a, score_b=score_b, first_goal=first_goal, user=current_user, is_default_bet=False)
            db.session.add(bet)
            saved_count += 1
        db.session.commit()
        if saved_count:
            flash(_('Your predictions have been saved!'), 'success')
        else:
            flash(_('No predictions were saved. Enter scores and choose a first goal option for each game you want to update.'), 'warning')
        return redirect(url_for('place_predictions'))
    return render_template("place_predictions.html", title=_('Place Predictions'), sport=g.sport, games=games, forms=forms, game_id=get_next_game())

@app.route('/games/<idd>', methods=['GET', 'POST'])
@login_required
def games(idd):
    games = Game.query.order_by(Game.id.asc()).all()
    bets = Bet.query.filter(Bet.user_id==current_user.id).join(Game).filter(or_(Bet.is_default_bet==False, Game.starts_at<utcnow())).all() 
    game_chosen = Game.query.filter(Game.id==idd).first_or_404()
    bets_to_show = Bet.query.filter(Bet.game_id==idd).options(joinedload(Bet.user)).all()
    bets_to_show.sort(key=lambda bet: (
        bet.user_id != current_user.id,
        bet.points is None,
        -(bet.points or 0),
    ))
    game_stats = db.session.query(
        func.count(Bet.id).label('all_bets'),
        func.sum(case((Bet.is_default_bet == True, 1), else_=0)).label('default_bets'),
        func.sum(case((Bet.winner_correct == True, 1), else_=0)).label('correct_winners'),
        func.sum(case((Bet.first_goal_correct == True, 1), else_=0)).label('correct_first_goals'),
        func.sum(case((Bet.score_diff_correct == True, 1), else_=0)).label('correct_score_diff'),
        func.sum(case((Bet.score_correct == True, 1), else_=0)).label('correct_score'),
    ).filter(Bet.game_id == idd).first()
    all_bets = game_stats.all_bets or 0
    default_bets = game_stats.default_bets or 0
    correct_winners = game_stats.correct_winners or 0
    correct_first_goals = game_stats.correct_first_goals or 0
    correct_score_diff = game_stats.correct_score_diff or 0
    correct_score = game_stats.correct_score or 0
    points_row = db.session.query(
        func.avg(Bet.points),
        func.max(Bet.points),
    ).filter(Bet.game_id==idd, Bet.points.isnot(None)).first()
    avg_points = round(points_row[0], 1) if points_row and points_row[0] is not None else None
    max_points = points_row[1] if points_row and points_row[1] is not None else None
    current_time = utcnow()
    three_hours_earlier = utcnow() - timedelta(hours=3)
    form = PlaceBetForm()
    form.first_goal.choices = first_goal_choices(game_chosen.team_a, game_chosen.team_b)
    if form.validate_on_submit():
        if game_chosen.starts_at < current_time: 
            flash(_('This game has started'))
            return redirect(url_for('games', idd=idd))
        bet_error = validate_bet_scores(form.score_a.data, form.score_b.data, form.first_goal.data, g.sport)
        if bet_error:
            flash(_(bet_error))
            return redirect(url_for('games', idd=idd))
        current_user.bets.filter_by(game_id=idd).delete()
        bet = Bet(game_id=idd, score_a = form.score_a.data, score_b = form.score_b.data, first_goal = form.first_goal.data, user=current_user, is_default_bet=False)
        db.session.add(bet)
        db.session.commit()
        flash(_('Your prediction has been saved.'))
        return redirect(url_for('games', idd=idd))
    return render_template("games.html", title=_('Games'), sport=g.sport, games=games, bets=bets, form=form, bets_to_show=bets_to_show, correct_winners=correct_winners, correct_first_goals=correct_first_goals, correct_score_diff=correct_score_diff, correct_score=correct_score, default_bets=default_bets, all_bets=all_bets, avg_points=avg_points, max_points=max_points, game_chosen=game_chosen, current_time=current_time, three_hours_earlier=three_hours_earlier, game_id=get_next_game())  
    
@app.route('/winner_prediction', methods=['GET', 'POST'])
@login_required
def winner_prediction():
    if request.method == 'GET':
        return redirect(url_for('user', username=current_user.username, setup='winner'))
    form = PlaceWinnerForm()
    form.final_winner.choices = winner_team_choices()
    if form.validate_on_submit():
        current_user.final_winner = form.final_winner.data
        current_user.final_winner_timestamp = utcnow()
        db.session.commit()
        flash(_('Your prediction has been saved.'))
        return redirect(url_for('user', username=current_user.username))
    return redirect(url_for('user', username=current_user.username, setup='winner'))
    
@app.route('/default_prediction', methods=['GET', 'POST'])
@login_required
def default_prediction():
    if request.method == 'GET':
        return redirect(url_for('user', username=current_user.username, setup='default'))
    form = PlaceBetForm()
    form.first_goal.choices = first_goal_choices(generic=True)
    if form.validate_on_submit():
        bet_error = validate_bet_scores(form.score_a.data, form.score_b.data, form.first_goal.data, g.sport)
        if bet_error:
            flash(_(bet_error))
            return redirect(url_for('user', username=current_user.username, setup='default'))
        current_user.default_score_a = form.score_a.data
        current_user.default_score_b = form.score_b.data
        current_user.default_first_goal = form.first_goal.data
        db.session.commit()
        for game in Game.query.filter(Game.starts_at>utcnow()).all():
            current_user.bets.filter_by(is_default_bet=True).filter_by(game_id=game.id).delete()
            list_of_bets = Bet.query.filter_by(user_id=current_user.id).filter_by(game_id=game.id).all()
            if len(list_of_bets)==0:
                bet = Bet(game_id=game.id, score_a = form.score_a.data, score_b = form.score_b.data, first_goal = form.first_goal.data, user=current_user, is_default_bet=True)
                db.session.add(bet)
        db.session.commit()    	
        flash(_('Your default prediction has been set.'))
        return redirect(url_for('user', username=current_user.username))
    return redirect(url_for('user', username=current_user.username, setup='default'))
                                                  
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash(_('Invalid username or password'))
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title=_('Login'), sport=g.sport, form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/language/<language>')
def set_language(language):
    if language in app.config['LANGUAGES']:
        session['lang'] = language
    return redirect(request.referrer or url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data, final_winner_points=0, total_score=0, total_score_diff=0, total_winner=0, total_first_goal=0, total_points=0, total_closed_bets=0, overall_points=0)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush() 
        if user.id == 1:
            user.is_admin = True
        db.session.commit()
        flash(_('Congratulations, you are now a registered user!'))
        return redirect(url_for('login'))
    return render_template('register.html', title=_('Register'), sport=g.sport, form=form)

@app.route('/user/<username>')
@login_required
def user(username):
    profile_user = User.query.filter_by(username=username).first_or_404()
    return _render_user_profile(profile_user, setup=request.args.get('setup'))

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'GET':
        return redirect(url_for('user', username=current_user.username, setup='profile'))
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash(_('Your changes have been saved.'))
        return redirect(url_for('user', username=current_user.username))
    return _render_user_profile(current_user, setup='profile', profile_form=form)                         

@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash(_('Check your email for the instructions to reset your password.'))
        return redirect(url_for('login'))
    return render_template('reset_password_request.html', title=_('Reset Password'), sport=g.sport, form=form)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(_('Your password has been reset.'))
        return redirect(url_for('login'))
    return render_template('reset_password.html', title=_('Reset Password'), sport=g.sport, form=form)
    
@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    # admins section
    current_admins = User.query.filter(User.is_admin == True).all()
    add_admin_form = AdminsForm(prefix="add")
    add_admin_form.users.choices = [(u.id, f'{u.username}') for u in User.query.filter(User.is_admin != True).all()]
    add_admin_form.users.coerce = int
    if _submitted(add_admin_form) and add_admin_form.validate():
        user_id = add_admin_form.users.data
        new_admin = User.query.get(user_id)
        if new_admin: #checks the user exists
            new_admin.is_admin = True
            db.session.commit()
            flash(_(f'{new_admin.username} has been granted admin rights.'), 'success')
            return redirect(url_for('admin'))
    remove_admin_form = AdminsForm(prefix="remove")
    remove_admin_form.users.choices = [(u.id, f'{u.username}') for u in current_admins]
    remove_admin_form.users.coerce = int
    if _submitted(remove_admin_form) and remove_admin_form.validate():
        user_id = remove_admin_form.users.data
        old_admin = User.query.get(user_id)
        if old_admin: #checks the user exists
            old_admin.is_admin = False
            db.session.commit()
            flash(_(f'{old_admin.username} has been taken away admin rights.'), 'success')
            return redirect(url_for('admin'))
    
    # users section
    remove_user_form = AdminsForm(prefix="remove_user")
    remove_user_form.users.choices = [(u.id, f'{u.username} - last seen at {u.last_seen} - placed {u.bets.count()} bets') for u in User.query.all()]
    remove_user_form.users.coerce = int
    if _submitted(remove_user_form) and remove_user_form.validate():
        user_id = remove_user_form.users.data
        old_user = User.query.get(user_id)
        if old_user: #checks the user exists
            old_user.is_shown = False
            db.session.commit()
            flash(_(f'{old_user.username} has been removed from the website standings.'), 'success')
            return redirect(url_for('admin'))

    # set games section 
    set_game_form = SetGame(prefix='set_game')
    set_game_form.game_id.choices = [(g.id, f'Game {g.id}: {g.team_a}-{g.team_b}, {g.stage}, {g.starts_at}') for g in Game.query.filter(Game.team_a == 'TBD').order_by(Game.starts_at.asc(), Game.id.asc()).all()]
    if _submitted(set_game_form) and set_game_form.validate():
        selected_game = Game.query.filter(Game.id==set_game_form.game_id.data).first()
        selected_game.team_a = set_game_form.team_a.data
        selected_game.team_b = set_game_form.team_b.data
        db.session.commit()
        flash(_('The game has been set.'))
        return redirect(url_for('admin'))

    # games score section 
    upload_csv_form = UploadCSVForm(prefix='upload_game_schedule')
    upload_winnerbet_csv_form = UploadCSVForm(prefix='upload_winner_bet_points')
    form = UploadResultsForm(prefix='upload_game_score')
    form.game_id.choices = [(g.id, f'Game {g.id}: {g.team_a}-{g.team_b}, {g.stage}') for g in Game.query.filter(Game.starts_at<utcnow()).filter(Game.score_a == None).order_by(Game.starts_at.asc(), Game.id.asc()).all()]
    form.first_goal.choices = first_goal_choices(generic=True)
    if _submitted(form) and form.validate():
        current_game = Game.query.filter(Game.id==form.game_id.data).first()
        current_game.score_a = form.score_a.data
        current_game.score_b = form.score_b.data
        current_game.first_goal = form.first_goal.data
        bets_to_update = Bet.query.join(Game).filter((Game.id==form.game_id.data)).all()
        for bet in bets_to_update:
            apply_bet_scoring(bet, current_game, g.sport)
        for u in User.query.all():
            u.total_score = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.score_correct == True, 1), else_=0)), 0))
            u.total_score_diff = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.score_diff_correct == True, 1), else_=0)), 0))
            u.total_winner = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.winner_correct == True, 1), else_=0)), 0))
            u.total_first_goal = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.first_goal_correct == True, 1), else_=0)), 0))
            u.total_points =  User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(Bet.points), 0))  
            u.overall_points = u.total_points
            u.total_closed_bets = User.query.filter(User.id==u.id).join(Bet).join(Game).filter(Game.first_goal>0).with_entities(func.count(Bet.points)) #Game.starts_at<(utcnow()-timedelta(hours=3))
        db.session.commit()
        flash(_('The results have been saved.'))
        return redirect(url_for('admin'))

    correct_game_score_form = UploadResultsForm(prefix='correct_game_score')
    correct_game_score_form.game_id.choices = [(g.id, f'Game {g.id}: {g.team_a}-{g.team_b}, {g.stage}') for g in Game.query.filter(Game.starts_at<utcnow()).filter(Game.score_a != None).order_by(Game.starts_at.asc(), Game.id.asc()).all()]
    correct_game_score_form.first_goal.choices = first_goal_choices(generic=True)
    if _submitted(correct_game_score_form) and correct_game_score_form.validate():
        current_game = Game.query.filter(Game.id==correct_game_score_form.game_id.data).first()
        current_game.score_a = correct_game_score_form.score_a.data
        current_game.score_b = correct_game_score_form.score_b.data
        current_game.first_goal = correct_game_score_form.first_goal.data
        bets_to_update = Bet.query.join(Game).filter((Game.id==correct_game_score_form.game_id.data)).all()
        for bet in bets_to_update:
            apply_bet_scoring(bet, current_game, g.sport)
        for u in User.query.all():
            u.total_score = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.score_correct == True, 1), else_=0)), 0))
            u.total_score_diff = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.score_diff_correct == True, 1), else_=0)), 0))
            u.total_winner = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.winner_correct == True, 1), else_=0)), 0))
            u.total_first_goal = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case((Bet.first_goal_correct == True, 1), else_=0)), 0))
            u.total_points =  User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(Bet.points), 0))  
            u.overall_points = u.total_points
            u.total_closed_bets = User.query.filter(User.id==u.id).join(Bet).join(Game).filter(Game.first_goal>0).with_entities(func.count(Bet.points)) #Game.starts_at<(utcnow()-timedelta(hours=3))
        db.session.commit()
        flash(_('The results have been corrected.'))
        return redirect(url_for('admin'))
    
    # winner team section 
    wform = PlaceWinnerForm()
    wform.final_winner.choices = winner_team_choices()
    if _submitted(wform) and wform.validate():
        for u in User.query.all():
            if u.final_winner==wform.final_winner.data:
                for i in Winnerbet.query.all():
                    if u.final_winner_timestamp>i.last_bet: 
                        continue
                    else:
                        u.final_winner_points = i.bet_points 
                        break
                u.overall_points += u.final_winner_points
        db.session.commit()
        flash(_('The winner has been set.'))
        return redirect(url_for('admin'))

    return render_template("admin.html", title=_('Admin'), sport=g.sport, admins=current_admins, 
                           aaform=add_admin_form, raform=remove_admin_form, ruform=remove_user_form, 
                           ug_csv_form=upload_csv_form, uw_csv_form=upload_winnerbet_csv_form, sgform=set_game_form, 
                           form=form, cgsform=correct_game_score_form,
                           wform=wform, game_id=get_next_game())

@app.route('/upload_csv', methods=['POST'])
@admin_required
def upload_csv():
    form = UploadCSVForm(prefix='upload_game_schedule')
    if form.validate_on_submit():
        file = form.csv_file.data
        try:
            stream = TextIOWrapper(file.stream, encoding='utf-8')
            csv_input = csv.DictReader(stream)
            for row in csv_input:
                if not all(k in row for k in ('team_a', 'team_b', 'stage', 'starts_at')):
                    flash('Missing required columns in CSV.', 'danger')
                    return redirect(url_for('admin'))
                try:
                    starts_at = datetime.strptime(row['starts_at'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    flash(f"Invalid date format in row: {row}", 'danger')
                    continue
                game = Game(team_a=row['team_a'].strip(), team_b=row['team_b'].strip(), stage=row['stage'].strip(), starts_at=starts_at)
                db.session.add(game)
            db.session.commit()
            flash('Games have been uploaded successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing CSV: {e}', 'danger')
    else:
        flash('Invalid file or form submission.', 'danger')
    return redirect(url_for('admin'))

@app.route('/upload_winnerbet_csv', methods=['POST'])
@admin_required
def upload_winnerbet_csv():
    form = UploadCSVForm(prefix='upload_winner_bet_points')
    if form.validate_on_submit():
        file = form.csv_file.data
        try:
            stream = TextIOWrapper(file.stream, encoding='utf-8')
            csv_input = csv.DictReader(stream)
            for row in csv_input:
                if not all(k in row for k in ('description', 'last_bet', 'bet_points')):
                    flash('Missing required columns in CSV.', 'danger')
                    return redirect(url_for('admin'))
                try:
                    last_bet = datetime.strptime(row['last_bet'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    flash(f"Invalid date format in row: {row}", 'danger')
                    continue
                try:
                    bet_points = int(row['bet_points'])
                except ValueError:
                    flash(f"Invalid bet_points in row: {row}", 'danger')
                    continue
                wb = Winnerbet(description=row['description'].strip(), last_bet=last_bet, bet_points=bet_points)
                db.session.add(wb)
            db.session.commit()
            flash('Winnerbet CSV uploaded successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing Winnerbet CSV: {e}', 'danger')
    else:
        flash('Invalid file or form submission.', 'danger')
    return redirect(url_for('admin'))
