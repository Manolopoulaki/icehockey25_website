from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from flask_babel import _, lazy_gettext as _l
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, IntegerField, SelectField
from wtforms.validators import ValidationError, DataRequired, InputRequired, Email, EqualTo, Length
from app.models import User

class LoginForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Remember Me'))
    submit = SubmitField(_l('Sign In'))

class RegistrationForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(), Length(max=20)])
    name = StringField(_l('Name'), validators=[DataRequired()])
    email = StringField(_l('Email'), description=_l('This is used only for password reseting and so we can reach you if you win!'), validators=[DataRequired(), Email()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(_l('Repeat Password'), validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Register'))

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError(_l('Please use a different username.'))

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError(_l('Please use a different email address.'))

class EditProfileForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(), Length(max=20)]) 
    about_me = TextAreaField(_l('About me'), validators=[Length(min=0, max=140)])
    submit = SubmitField(_l('Save changes'))
    
    def __init__(self, original_username, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError(_l('Please use a different username.'))
    
class PostForm(FlaskForm):
    post = TextAreaField(_l('Say something'), validators=[DataRequired(), Length(min=1, max=140)])
    submit = SubmitField(_l('Post'))
    
class NewSelectField(SelectField):
    def pre_validate(self, form):
        pass
    
    def process_formdata(self, valuelist):
        if valuelist:
            self.data=",".join(valuelist)
        else:
            self.data="'"

class PlaceBetForm(FlaskForm): 
    score_a = IntegerField(_l('Score of Team A'), validators=[InputRequired()], render_kw={"inputmode": "numeric"})
    score_b = IntegerField(_l('Score of Team B'), validators=[InputRequired()], render_kw={"inputmode": "numeric"})
    first_goal = NewSelectField(_l('First Goal'), validators=[DataRequired()], coerce=str)
    submit = SubmitField(_l('Place Prediction'))
    
class UploadResultsForm(FlaskForm): 
    game_id = NewSelectField(_l('Game'), validators=[DataRequired()], coerce=int)
    score_a = IntegerField(_l('Score of Team A'), validators=[InputRequired()], render_kw={"inputmode": "numeric"})
    score_b = IntegerField(_l('Score of Team B'), validators=[InputRequired()], render_kw={"inputmode": "numeric"})
    first_goal = NewSelectField(_l('First Goal'), validators=[DataRequired()], coerce=str)
    submit = SubmitField(_l('Upload Result'))

class UploadCSVForm(FlaskForm):
    csv_file = FileField(_('CSV File'), validators=[FileRequired(), FileAllowed(['csv'], _('CSV files only!'))])
    submit = SubmitField('Upload')

class SetGame(FlaskForm):
    game_id = NewSelectField(_l('Game'), validators=[DataRequired()], coerce=int)
    team_a = StringField(_l('Team A'), validators=[DataRequired(), Length(max=3)]) 
    team_b = StringField(_l('Team B'), validators=[DataRequired(), Length(max=3)])
    submit = SubmitField(_l('Set Game'))
    
class PlaceWinnerForm(FlaskForm): 
    final_winner = NewSelectField(_l('Tournament Winner'), validators=[DataRequired()], coerce=str)
    submit = SubmitField(_l('Submit'))

class AdminsForm(FlaskForm): 
    users = NewSelectField(_l('Users'), validators=[DataRequired()], coerce=str)
    submit = SubmitField(_l('Save')) 

class ResetPasswordRequestForm(FlaskForm):
    email = StringField(_l('Email'), validators=[DataRequired(), Email()])
    submit = SubmitField(_l('Request Password Reset'))

class ResetPasswordForm(FlaskForm):
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    password2 = PasswordField(
        _l('Repeat Password'), validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField(_l('Request Password Reset'))
