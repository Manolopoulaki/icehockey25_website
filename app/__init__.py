import logging
from logging.handlers import SMTPHandler, RotatingFileHandler
import os
from datetime import timezone
from flask import Flask, session
from flask import request
from config import Config
from markupsafe import Markup
import jinja2
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
jinja2.Markup = Markup
from flask_moment import Moment
from flask_babel import Babel

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
migrate = Migrate(app, db, compare_type=True)
login = LoginManager(app)
login.login_view = 'login'
login.login_message = ''
mail = Mail(app)
moment = Moment(app)

def as_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

app.jinja_env.globals['as_utc'] = as_utc

from app.teams import team_name_filter
app.jinja_env.filters['team_name'] = team_name_filter

def get_locale():
    #return request.accept_languages.best_match(app.config['LANGUAGES'])
	return session.get('lang', 'en')

babel = Babel()
try:
	babel.init_app(app, locale_selector=get_locale)
except TypeError:
	babel.init_app(app)
	if hasattr(babel, 'localeselector'):
		@babel.localeselector
		def _legacy_locale_selector():
			return get_locale()

if not app.debug and not app.testing:
	if app.config['MAIL_SERVER']:
		auth = None
		if app.config['MAIL_USERNAME'] or app.config['MAIL_PASSWORD']:
			auth = (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
		secure = None
		if app.config['MAIL_USE_TLS']:
			secure = ()
		mail_handler = SMTPHandler(
			mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
			fromaddr=app.config['ADMINS'],#'no-reply@' + app.config['MAIL_SERVER'],
			toaddrs=app.config['ADMINS'], subject='Website Failure',
			credentials=auth, secure=secure)
		mail_handler.setLevel(logging.ERROR)
		app.logger.addHandler(mail_handler)
	if app.config['LOG_TO_STDOUT']:
		stream_handler = logging.StreamHandler()
		stream_handler.setLevel(logging.INFO)
		app.logger.addHandler(stream_handler)
	else:
		if not os.path.exists('logs'):
			os.mkdir('logs')
		file_handler = RotatingFileHandler('logs/websitie.log',
			maxBytes=10240, backupCount=10)
		file_handler.setFormatter(logging.Formatter(
			'%(asctime)s %(levelname)s: %(message)s '
			'[in %(pathname)s:%(lineno)d]'))
		file_handler.setLevel(logging.INFO)
		app.logger.addHandler(file_handler)

	app.logger.setLevel(logging.INFO)
	app.logger.info('Website startup')

from app import routes, models, errors
