from datetime import datetime, timedelta
from pathlib import Path
import unittest
from app import app, db
from app.models import User, Post

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


class SecurityHookCase(unittest.TestCase):
    def test_pre_push_hook_runs_vulnerability_audit(self):
        hook_path = Path('.githooks/pre-push')
        self.assertTrue(hook_path.exists(), 'pre-push hook is missing')
        self.assertTrue(hook_path.is_file(), 'pre-push hook is not a file')
        self.assertTrue(hook_path.stat().st_mode & 0o111, 'pre-push hook is not executable')
        hook_text = hook_path.read_text(encoding='utf-8')
        self.assertIn('pip-audit', hook_text)
        self.assertIn('-r requirements.txt', hook_text)
                 
if __name__ == '__main__':
    unittest.main(verbosity=2)                          
