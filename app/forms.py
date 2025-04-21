from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, IntegerField, SelectField
from wtforms.validators import ValidationError, DataRequired, InputRequired, Email, EqualTo, Length
from app.models import User, Game

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class EditProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    about_me = TextAreaField('About me', validators=[Length(min=0, max=140)])
    submit = SubmitField('Submit')
    
    def __init__(self, original_username, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')
    
class PostForm(FlaskForm):
    post = TextAreaField('Say something', validators=[
        DataRequired(), Length(min=1, max=140)])
    submit = SubmitField('Submit')
    
class NewSelectField(SelectField):
    def pre_validate(self, form):
    	pass
	
    def process_formdata(self, valuelist):
    	if valuelist:
    		self.data=",".join(valuelist)
    	else:
    		self.data="'"

class PlaceBetForm(FlaskForm): 
    score_a = IntegerField('Score of Team A', validators=[InputRequired()])
    score_b = IntegerField('Score of Team B', validators=[InputRequired()])
    first_goal = NewSelectField('First Goal', validators=[DataRequired()], coerce=str)
    submit = SubmitField('Place Prediction')
    
class PlaceWinnerForm(FlaskForm): 
    final_winner = NewSelectField('Tournament Winner', validators=[DataRequired()], coerce=str)
    submit = SubmitField('Submit')
    
class UploadResultsForm(FlaskForm): 
    game_id = NewSelectField('Game', validators=[DataRequired()], coerce=int)
    score_a = IntegerField('Score A', validators=[InputRequired()])
    score_b = IntegerField('Score B', validators=[InputRequired()])
    first_goal = NewSelectField('First Goal', validators=[DataRequired()], coerce=str)
    submit = SubmitField('Submit Result')
    
class ResetPasswordRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Request Password Reset')
