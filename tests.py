from datetime import datetime, timedelta
from pathlib import Path
import unittest
from app import app, db
from app.models import User, Post, Game
from app.routes import get_next_game

class UserModelCase(unittest.TestCase):
    def setUp(self):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_password_hashing(self):
        u = User(username='susan')
        u.set_password('cat')
        self.assertFalse(u.check_password('dog'))
        self.assertTrue(u.check_password('cat'))

    def test_avatar(self):
        u = User(username='john', email='john@example.com')
        self.assertEqual(u.avatar(128), ('https://www.gravatar.com/avatar/'
                                         'd4c74594d841139328695756648b6bd6'
                                         '?d=identicon&s=128'))

    def test_get_next_game_returns_none_without_schedule(self):
        self.assertIsNone(get_next_game())

    def test_get_next_game_returns_next_upcoming_game(self):
        past_game = Game(id=1, team_a='AUT', team_b='LAT',
                         starts_at=datetime.utcnow() - timedelta(days=1))
        next_game = Game(id=2, team_a='CAN', team_b='USA',
                         starts_at=datetime.utcnow() + timedelta(hours=1))
        later_game = Game(id=3, team_a='FIN', team_b='SWE',
                          starts_at=datetime.utcnow() + timedelta(days=1))
        db.session.add_all([past_game, next_game, later_game])
        db.session.commit()

        self.assertEqual(get_next_game(), next_game.id)

    def test_get_next_game_returns_last_game_after_tournament(self):
        first_game = Game(id=1, team_a='AUT', team_b='LAT',
                          starts_at=datetime.utcnow() - timedelta(days=2))
        last_game = Game(id=2, team_a='CAN', team_b='USA',
                         starts_at=datetime.utcnow() - timedelta(days=1))
        db.session.add_all([first_game, last_game])
        db.session.commit()

        self.assertEqual(get_next_game(), last_game.id)


class SecurityHookCase(unittest.TestCase):
    def test_pre_push_hook_runs_vulnerability_audit(self):
        hook_path = Path('.githooks/pre-push')
        self.assertTrue(hook_path.exists(), 'pre-push hook is missing')
        self.assertTrue(hook_path.is_file(), 'pre-push hook is not a file')
        self.assertTrue(hook_path.stat().st_mode & 0o111, 'pre-push hook is not executable')
        hook_text = hook_path.read_text(encoding='utf-8')
        self.assertIn('pip-audit', hook_text)
        self.assertIn('-r requirements.txt', hook_text)

    def test_hook_bootstrap_is_documented_and_configures_git(self):
        script_path = Path('scripts/setup-git-hooks.sh')
        readme_path = Path('README.md')
        self.assertTrue(script_path.exists(), 'bootstrap script is missing')
        self.assertTrue(readme_path.exists(), 'README is missing')
        script_text = script_path.read_text(encoding='utf-8')
        readme_text = readme_path.read_text(encoding='utf-8')
        self.assertIn('git config core.hooksPath .githooks', script_text)
        self.assertIn('scripts/setup-git-hooks.sh', readme_text)
        self.assertIn('.githooks/pre-push', readme_text)
                 
if __name__ == '__main__':
    unittest.main(verbosity=2)                          
