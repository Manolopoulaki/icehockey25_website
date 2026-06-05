from datetime import datetime

from flask import current_app
from markupsafe import Markup, escape


default_jquery_version = '3.4.1'
default_jquery_sri = 'sha256-CSXorXvZcTkaix6Yvo6HppcZGetbYMGWSFlBw8HfCJo='
default_moment_version = '2.24.0'
default_moment_sri = 'sha256-AdQN98MVZs44Eq2yTwtoKufhnU+uZ7v2kXnD5vqzZVo='


class _MomentProxy:
    def __init__(self, dt):
        self.dt = dt

    def _timestamp(self):
        if isinstance(self.dt, datetime):
            return self.dt.isoformat()
        return str(self.dt)

    def format(self, fmt):
        return Markup(
            f'<span class="flask-moment" data-timestamp="{escape(self._timestamp())}" '
            f'data-format="format(\'{escape(fmt)}\')"></span>'
        )

    def fromNow(self):
        return Markup(
            f'<span class="flask-moment" data-timestamp="{escape(self._timestamp())}" '
            'data-format="fromNow()"></span>'
        )


class Moment:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.jinja_env.globals['moment'] = self
        return app

    def __call__(self, dt):
        return _MomentProxy(dt)

    @staticmethod
    def include_moment(version=default_moment_version, local_js=None, no_js=None, sri=None):
        js = ''
        if version == default_moment_version and local_js is None and sri is None:
            sri = default_moment_sri
        if not no_js:
            if local_js is not None:
                if not sri:
                    js = '<script src="{}"></script>\n'.format(local_js)
                else:
                    js = '<script src="{}" integrity="{}" crossorigin="anonymous"></script>\n'.format(local_js, sri)
            elif version is not None:
                js_filename = 'moment-with-locales.min.js'
                if not sri:
                    js = '<script src="//cdnjs.cloudflare.com/ajax/libs/moment.js/{}/{}"></script>\n'.format(version, js_filename)
                else:
                    js = '<script src="//cdnjs.cloudflare.com/ajax/libs/moment.js/{}/{}" integrity="{}" crossorigin="anonymous"></script>\n'.format(version, js_filename, sri)

        default_format = ''
        if 'MOMENT_DEFAULT_FORMAT' in current_app.config:
            default_format = '\nmoment.defaultFormat = "{}";'.format(current_app.config['MOMENT_DEFAULT_FORMAT'])
        return Markup(
            js
            + '<script>\n'
            + 'moment.locale("en");'
            + default_format
            + '\nfunction flask_moment_render(elem) {\n'
            + '    $(elem).text(eval(\'moment("\' + $(elem).data(\'timestamp\') + \'").\' + $(elem).data(\'format\') + \';\'));\n'
            + "    $(elem).removeClass('flask-moment').show();\n"
            + '}\n'
            + 'function flask_moment_render_all() {\n'
            + "    $('.flask-moment').each(function() {\n"
            + '        flask_moment_render(this);\n'
            + "        if ($(this).data('refresh')) {\n"
            + '            (function(elem, interval) { setInterval(function() { flask_moment_render(elem) }, interval); })(this, $(this).data(\'refresh\'));\n'
            + '        }\n'
            + '    })\n'
            + '}\n'
            + '$(document).ready(function() {\n'
            + '    flask_moment_render_all();\n'
            + '});\n'
            + '</script>'
        )

    @staticmethod
    def include_jquery(version=default_jquery_version, local_js=None, sri=None):
        js = ''
        if sri is None and version == default_jquery_version and local_js is None:
            sri = default_jquery_sri
        if local_js is not None:
            if not sri:
                js = '<script src="{}"></script>\n'.format(local_js)
            else:
                js = '<script src="{}" integrity="{}" crossorigin="anonymous"></script>\n'.format(local_js, sri)
        elif version is not None:
            if not sri:
                js = '<script src="//ajax.googleapis.com/ajax/libs/jquery/{}/jquery.min.js"></script>\n'.format(version)
            else:
                js = '<script src="//ajax.googleapis.com/ajax/libs/jquery/{}/jquery.min.js" integrity="{}" crossorigin="anonymous"></script>\n'.format(version, sri)
        return Markup(js)

    @staticmethod
    def lang(lang):
        return Markup('<script>moment.locale("{}");</script>'.format(lang))
