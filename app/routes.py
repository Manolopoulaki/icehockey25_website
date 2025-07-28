from flask import render_template, flash, redirect, request, url_for, g, session
from app import app, db
from app.forms import LoginForm, RegistrationForm, PostForm, ResetPasswordRequestForm, ResetPasswordForm, EditProfileForm, PlaceBetForm, PlaceWinnerForm, UploadResultsForm
from flask_login import current_user, login_user, logout_user, login_required
from app.models import User, Post, Game, Bet, Winnerbet
from werkzeug.urls import url_parse
from app.email import send_password_reset_email
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func, case
from sqlalchemy.sql.functions import coalesce
from flask_babel import get_locale
from flask_babel import _

@app.before_request
def before_request():
    g.sport = app.config['SPORT']
    g.locale = str(get_locale())
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        
        
def get_next_game():
    is_next_game = Game.query.filter(Game.starts_at > datetime.utcnow()).order_by(Game.starts_at.asc(), Game.id.asc()).first()
    if is_next_game == None: 
        return Game.query.order_by(Game.id.desc()).first()
    else: 
        return is_next_game
        
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
        page, app.config['POSTS_PER_PAGE'], False)#current_user.get_own_posts().all()
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

    next_game = get_next_game()
    return render_template("index.html", title='Home', sport=g.sport, form=form, posts=posts.items,
    			    next_url=next_url, prev_url=prev_url, leaders=leaders_dict, game_id=next_game.id)

@app.route('/rules', methods=['GET', 'POST'])
@login_required
def rules():
    winner_bet = Winnerbet.query.all()
    next_game = get_next_game()
    return render_template("rules.html", title='Rules', winner_bet=winner_bet, sport=g.sport, game_id=next_game.id)
    
@app.route('/standings', methods=['GET', 'POST'])
@login_required
def standings():
    results = User.query.with_entities(func.rank().over(order_by=(User.overall_points.desc(), User.total_score.desc(), User.total_score_diff.desc(), User.total_winner.desc(), User.total_first_goal.desc())).label('ranking')).order_by('ranking').add_columns(User.username, User.overall_points, User.final_winner_points, User.total_score, User.total_score_diff, User.total_winner, User.total_first_goal, User.total_points, User.total_closed_bets).all()
    next_game = get_next_game()
    return render_template("standings.html", title='Standings', sport=g.sport, results=results, game_id=next_game.id)
    
@app.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    games = Game.query.order_by(Game.id.asc()).all()
    current_time = datetime.utcnow()
    three_hours_earlier = datetime.utcnow() - timedelta(hours=3)
    next_game = get_next_game()
    return render_template("schedule.html", title='Schedule', sport=g.sport, games=games, game_id=next_game.id, current_time=current_time, three_hours_earlier=three_hours_earlier)
    
@app.route('/place_predictions', methods=['GET', 'POST'])
@login_required
def place_predictions():
    current_time = datetime.utcnow()
    games = Game.query.filter(and_(Game.team_a != 'TBD', Game.team_b != 'TBD', Game.starts_at > current_time)).order_by(Game.id.asc()).all()
    forms = {}
    
    for game in games:
        form = PlaceBetForm()
        forms[game.id] = form
        form.first_goal.choices = [(iteam, team) for iteam, team in zip([0,1,2], [_('First Goal'), f'Team {game.team_a}', f'Team {game.team_b}'])]
        existing_bet = current_user.bets.filter(and_(Bet.game_id==game.id, Bet.is_default_bet==False)).first()
        if existing_bet:
            form.score_a.data = existing_bet.score_a
            form.score_b.data = existing_bet.score_b
            form.first_goal.data = str(existing_bet.first_goal)

    if request.method == 'POST':
        for game in games:
            try:
                score_a = int(request.form.get(f'score_a_{game.id}', 0))
                score_b = int(request.form.get(f'score_b_{game.id}', 0))
                first_goal = int(request.form.get(f'first_goal_{game.id}', 0))
            except (ValueError, TypeError):
                flash(_('Invalid input for game %(game)s.', game=game.id), 'danger')
                continue
            if game.starts_at < current_time:
                flash(_('This game (%(gamea)s vs %(gameb)s) has already started.', gamea=game.team_a, gameb=game.team_b), 'danger')
                continue
            elif (score_a == 0 and score_b == 0 and int(first_goal) != 0) or \
                 (score_a == 0 and score_b != 0 and int(first_goal) != 2) or \
                 (score_a != 0 and score_b == 0 and int(first_goal) != 1) or \
                 (score_a != 0 and score_b != 0 and int(first_goal) == 0):
                flash(_('Your first goal prediction is not valid for game %(game)s.', game=game.id), 'danger')
                continue
            elif (score_a == 0 and score_b == 0 and first_goal == 0):
                continue
            elif score_a == score_b  and g.sport == 'hockey':
                flash(_('Your prediction for game %(game)s cannot be a draw.', game=game.id), 'danger')
                continue
            else:
                current_user.bets.filter_by(game_id=game.id).delete()
                bet = Bet(game_id=game.id, score_a=score_a, score_b=score_b, first_goal=first_goal, user=current_user, is_default_bet=False)
                db.session.add(bet)
        db.session.commit()
        flash(_('Your predictions have been saved!'), 'success')
        return redirect(url_for('place_predictions'))
    next_game = get_next_game()
    return render_template("place_predictions.html", title='Place Predictions', sport=g.sport,games=games, forms=forms, game_id=next_game.id)

@app.route('/games/<idd>', methods=['GET', 'POST'])
@login_required
def games(idd):
    games = Game.query.order_by(Game.id.asc()).all()
    bets = Bet.query.filter(Bet.user_id==current_user.id).join(Game).filter(or_(Bet.is_default_bet==False, Game.starts_at<datetime.utcnow())).all() 
    game_chosen = Game.query.filter(Game.id==idd).first_or_404()
    bets_to_show = Bet.query.filter(Bet.game_id==idd).order_by(Bet.timestamp.asc()).join(Game).add_columns(Bet.user_id, Game.id, Game.team_a, Game.team_b, Bet.score_a, Bet.score_b, Bet.first_goal, Bet.points, Bet.is_default_bet)
    correct_winners = Bet.query.filter(Bet.game_id==idd).filter(Bet.winner_correct==True).count()
    correct_first_goals = Bet.query.filter(Bet.game_id==idd).filter(Bet.first_goal_correct==True).count()
    default_bets = Bet.query.filter(Bet.game_id==idd).filter(Bet.is_default_bet==True).count()
    all_bets = Bet.query.filter(Bet.game_id==idd).count()
    users = User.query.add_columns(User.id, User.username)
    current_time = datetime.utcnow()
    three_hours_earlier = datetime.utcnow() - timedelta(hours=3)
    form = PlaceBetForm()
    form.first_goal.choices = [(iteam, team) for iteam, team in zip([0,1,2], [_('First Goal'), _('Team %(teama)s', teama=game_chosen.team_a), _('Team %(teamb)s', teamb=game_chosen.team_b)])]
    if form.validate_on_submit():
        if game_chosen.starts_at < current_time: 
            flash(_('This game has started'))
            return redirect(url_for('games', idd=idd))
        if ((form.score_a.data == 0 and form.score_b.data == 0 and int(form.first_goal.data)!=0) or (form.score_a.data == 0 and form.score_b.data != 0 and int(form.first_goal.data)!=2) or     	(form.score_a.data != 0 and form.score_b.data == 0 and int(form.first_goal.data)!=1) or (form.score_a.data!=0 and form.score_b.data!=0 and int(form.first_goal.data)==0)): 
            flash(_('Your first goal prediction is not valid.'))
            return redirect(url_for('games', idd=idd))
        if form.score_a.data == form.score_b.data and g.sport == 'hockey':
            flash(_('Your prediction is not valid.'))
            return redirect(url_for('games', idd=idd))
        current_user.bets.filter_by(game_id=idd).delete()
        bet = Bet(game_id=idd, score_a = form.score_a.data, score_b = form.score_b.data, first_goal = form.first_goal.data, user=current_user, is_default_bet=False)
        db.session.add(bet)
        db.session.commit()
        flash(_('Your prediction has been saved.'))
        return redirect(url_for('games', idd=idd))
    next_game = get_next_game()
    return render_template("games.html", title='Games', sport=g.sport, games=games, bets=bets, form=form, bets_to_show=bets_to_show, correct_winners=correct_winners, correct_first_goals=correct_first_goals, default_bets=default_bets, all_bets=all_bets, game_chosen=game_chosen, users=users, current_time=current_time, three_hours_earlier=three_hours_earlier, game_id=next_game.id)  
    
@app.route('/winner_prediction', methods=['GET', 'POST'])
@login_required
def winner_prediction():
    form = PlaceWinnerForm()
    form.final_winner.choices = [(g.team, _('Team %(team)s', team=g.team)) for g in Game.query.filter(Game.team_a!='TBD').with_entities(Game.team_b.label('team')).union(Game.query.filter(Game.team_b!='TBD').with_entities(Game.team_a.label('team'))).distinct().all()]
    winner_bet = Winnerbet.query.all()
    if form.validate_on_submit():
        current_user.final_winner = form.final_winner.data
        current_user.final_winner_timestamp = datetime.utcnow()
        db.session.commit()
        flash(_('Your prediction has been saved.'))
        return redirect(url_for('user', username=current_user.username))
    next_game = get_next_game()
    return render_template("winner_prediction.html", title='Winner Prediction', sport=g.sport, form=form, winner_bet=winner_bet, game_id=next_game.id)
    
@app.route('/default_prediction', methods=['GET', 'POST'])
@login_required
def default_prediction():
    form = PlaceBetForm()
    form.first_goal.choices = [(iteam, team) for iteam, team in zip([0,1,2], [_('First Goal'), _('Team A'), _('Team B')])]
    if form.validate_on_submit():
        if ((form.score_a.data == 0 and form.score_b.data == 0 and int(form.first_goal.data)!=0) or (form.score_a.data == 0 and form.score_b.data != 0 and int(form.first_goal.data)!=2) or     	(form.score_a.data != 0 and form.score_b.data == 0 and int(form.first_goal.data)!=1) or (form.score_a.data!=0 and form.score_b.data!=0 and int(form.first_goal.data)==0)): 
            flash(_('Your first goal prediction is not valid.'))
            return redirect(url_for('default_prediction'))
        if form.score_a.data == form.score_b.data and g.sport == 'hockey':
            flash(_('Your prediction is not valid.'))
            return redirect(url_for('default_prediction'))
        current_user.default_score_a = form.score_a.data
        current_user.default_score_b = form.score_b.data
        current_user.default_first_goal = form.first_goal.data
        db.session.commit()
        for game in Game.query.filter(Game.starts_at>datetime.utcnow()).all():
            current_user.bets.filter_by(is_default_bet=True).filter_by(game_id=game.id).delete()
            list_of_bets = Bet.query.filter_by(user_id=current_user.id).filter_by(game_id=game.id).all()
            if len(list_of_bets)==0:
                bet = Bet(game_id=game.id, score_a = form.score_a.data, score_b = form.score_b.data, first_goal = form.first_goal.data, user=current_user, is_default_bet=True)
                db.session.add(bet)
        db.session.commit()    	
        flash(_('Your default prediction has been set.'))
        return redirect(url_for('user', username=current_user.username))
    next_game = get_next_game()
    return render_template("default_prediction.html", title='Default Prediction', sport=g.sport, form=form, game_id=next_game.id)
                                                  
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
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Login', sport=g.sport, form=form)

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
        user = User(username=form.username.data, email=form.email.data, name=form.name.data, final_winner_points=0, total_score=0, total_score_diff=0, total_winner=0, total_first_goal=0, total_points=0, total_closed_bets=0, overall_points=0)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(_('Congratulations, you are now a registered user!'))
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', sport=g.sport, form=form)

@app.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user.final_winner_timestamp:
        for i in Winnerbet.query.all():
            if user.final_winner_timestamp>i.last_bet: winner_bet_points = 0 #continue #TO CHECK
            else:
                winner_bet_points = i.bet_points 
                break	
    else: winner_bet_points = 0
    #page = request.args.get('page', 1, type=int)
    #posts = user.posts.order_by(Post.timestamp.desc()).paginate(
    #    page, app.config['POSTS_PER_PAGE'], False)
    #next_url = url_for('user', username=user.username, page=posts.next_num) \
    #    if posts.has_next else None
    #prev_url = url_for('user', username=user.username, page=posts.prev_num) \
    #    if posts.has_prev else None
    if user == current_user:
        bets = user.bets.order_by(Bet.game_id.asc()).join(Game).filter(or_(Bet.is_default_bet==False, Game.starts_at<datetime.utcnow())).add_columns(Game.id, Game.team_a, Game.team_b, Game.starts_at, Bet.score_a, Bet.score_b, Bet.first_goal, Game.score_a, Game.score_b, Game.first_goal, Bet.first_goal_correct, Bet.winner_correct, Bet.score_diff_correct, Bet.score_correct, Bet.points, Bet.is_default_bet) 
    else:
        bets = user.bets.order_by(Bet.game_id.asc()).join(Game).filter(Game.starts_at<datetime.utcnow()).add_columns(Game.id, Game.team_a, Game.team_b, Game.starts_at, Bet.score_a, Bet.score_b, Bet.first_goal, Game.score_a, Game.score_b, Game.first_goal, Bet.first_goal_correct, Bet.winner_correct, Bet.score_diff_correct, Bet.score_correct, Bet.points, Bet.is_default_bet) 
    stats = User.query.with_entities(func.rank().over(order_by=(User.overall_points.desc(), User.total_score.desc(), User.total_score_diff.desc(), User.total_winner.desc(), User.total_first_goal.desc())).label('ranking')).add_columns(User.username, User.total_score, User.total_score_diff, User.total_winner, User.total_first_goal, User.total_points, User.total_closed_bets, User.overall_points).all()    
    next_game = get_next_game()
    return render_template('user.html', title='Profile', sport=g.sport, user=user, bets=bets, stats=stats, winner_bet_points=winner_bet_points, game_id=next_game.id)
                           
@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash(_('Your changes have been saved.'))
        return redirect(url_for('user', username=current_user.username))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    next_game = get_next_game()
    return render_template('edit_profile.html', title='Edit Profile', sport=g.sport, form=form, game_id=next_game.id)                         

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
    return render_template('reset_password_request.html', title='Reset Password', sport=g.sport, form=form)

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
    return render_template('reset_password.html', title='Reset Password', sport=g.sport, form=form)
    
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    form = UploadResultsForm()
    form.game_id.choices = [(g.id, f'Game {g.id}: {g.team_a}-{g.team_b}, {g.stage}') for g in Game.query.filter(Game.starts_at<datetime.utcnow()).filter(Game.score_a == None).order_by(Game.starts_at.asc(), Game.id.asc()).all()]
    form.first_goal.choices = [(iteam, team) for iteam, team in zip([0,1,2], ['First Goal', 'Team A', 'Team B'])]
    if form.validate_on_submit():
        current_game = Game.query.filter(Game.id==form.game_id.data).first()
        current_game.score_a = form.score_a.data
        current_game.score_b = form.score_b.data
        current_game.first_goal = form.first_goal.data
        bets_to_update = Bet.query.join(Game).filter((Game.id==form.game_id.data)).all()
        for bet in bets_to_update:
            if (bet.first_goal==int(current_game.first_goal)): bet.first_goal_correct=True
            else: bet.first_goal_correct=False
            if (bet.score_a==current_game.score_a and bet.score_b==current_game.score_b): bet.score_correct=True
            else: bet.score_correct=False
            if (((bet.score_a>bet.score_b) and (current_game.score_a>current_game.score_b)) or ((bet.score_b>bet.score_a) and (current_game.score_b>current_game.score_a)) or ((bet.score_b==bet.score_a) and (current_game.score_b==current_game.score_a))):
                bet.winner_correct=True
            else: bet.winner_correct=False
            if (bet.winner_correct==True and abs(bet.score_a-bet.score_b)==abs(current_game.score_a-current_game.score_b)): bet.score_diff_correct=True
            else: bet.score_diff_correct=False
            if g.sport == 'hockey':
                bet.points = int(bet.first_goal_correct) + 3*int(bet.winner_correct) + int(bet.score_diff_correct) + 3*int(bet.score_correct)
            if g.sport == 'football':
                bet.points = int(bet.first_goal_correct) + 3*int(bet.winner_correct) + int(bet.score_diff_correct) + 2*int(bet.score_correct)
        for u in User.query.all():
            u.total_score = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case([(Bet.score_correct == True, 1)], else_=0)), 0))
            u.total_score_diff = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case([(Bet.score_diff_correct == True, 1)], else_=0)), 0))
            u.total_winner = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case([(Bet.winner_correct == True, 1)], else_=0)), 0))
            u.total_first_goal = User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(case([(Bet.first_goal_correct == True, 1)], else_=0)), 0))
            u.total_points =  User.query.filter(User.id==u.id).join(Bet).with_entities(coalesce(func.sum(Bet.points), 0))  
            u.overall_points = u.total_points
            u.total_closed_bets = User.query.filter(User.id==u.id).join(Bet).join(Game).filter(Game.first_goal>0).with_entities(func.count(Bet.points)) #Game.starts_at<(datetime.utcnow()-timedelta(hours=3))
        db.session.commit()
        flash(_('The results have been saved.'))
    
    wform = PlaceWinnerForm()
    wform.final_winner.choices = [(g.team, f'Team {g.team}') for g in Game.query.filter(Game.team_a!='TBD').with_entities(Game.team_b.label('team')).union(Game.query.filter(Game.team_b!='TBD').with_entities(Game.team_a.label('team'))).distinct().all()]
    if wform.validate_on_submit():
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
        flash(_('The winner have been set.'))
        return redirect(url_for('index'))
    next_game = get_next_game()
    return render_template("admin.html", title='Set Winner', sport=g.sport, form=form, wform=wform, game_id=next_game.id)