"""HTTP routes of the updater (settings -> Updates). A mixin of app.Handler. Installing and rolling back are separate presses of the creator;
the page never names a URL: the package is the one the feed in settings.json offered at the last check (luna/core/updater.py)."""
from luna.core import audit, updater


class UpdateRoutes:
    def handle_update(self):
        op = self.path[len('/update/'):]
        try:
            self.read_json(200)
            if op == 'state':
                return self.send(200, {'current': updater.current_version(), 'feed': bool(updater.feed_url()), 'backup': updater.has_backup()})
            if op == 'check':
                return self.send(200, updater.check())
            if op == 'install':
                out = updater.install()
                audit.log('update', out['version'])
                return self.send(200, out)
            if op == 'rollback':
                out = updater.rollback()
                audit.log('update.rollback', out['version'])
                return self.send(200, out)
            return self.send(404, {'error': 'Not found'})
        except updater.UpdateError as exc:
            return self.send(502 if str(exc) in ('net', 'feed') else 400, {'error': 'update:%s' % exc})
        except (ValueError, TypeError):
            return self.send(400, {'error': 'Некорректный запрос.'})
