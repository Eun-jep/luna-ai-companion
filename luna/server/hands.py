"""HTTP routes of her hands (documents, code, projects, commands, engines, providers, journal, nook, songs). A mixin of app.Handler: `self.send`,
`self.read_json` and the guard come from there. Every route works only on a token that a plate gave out and the creator pressed."""

from pathlib import Path
from urllib.parse import unquote

from luna import security
from luna.core import audit, providers
from luna.dev import codescan, devtools, envdiag, gitdiff, godot_bridge, sqlrun, unity_bridge, unreal_bridge
from luna.hands import codeedit, control, docfiles, nook, office, projects, runner, studio
from luna.senses import hearing
from luna.server.appref import _app



class HandsRoutes:
    def handle_control(self):
        """Mouse and keyboard task: start (after the creator's Start), step (look and propose), do (run one allowed action), stop."""
        try:
            body = self.read_json(_app().MAX_IMAGE + 20000)
            if self.path == '/agent/stop':
                _app().end_task()
                return self.send(200, {'ok': True})
            if self.path == '/agent/start':
                if not control.begin(body.get('token')):
                    return self.send(403, {'error': 'Задача не запрошена или устарела.'})
                audit.log('task', control.SESSION.get('task', ''))
                return self.send(200, {'ok': True})
            if self.path == '/agent/step':
                image, steps = body.get('image'), body.get('steps')
                lang = _app().LANGS.get(body.get('lang'), _app().LANGS['en'])
                if not (isinstance(image, str) and image.startswith('data:image/jpeg;base64,') and len(image) <= _app().MAX_IMAGE
                        and isinstance(steps, list) and all(isinstance(x, str) for x in steps)):
                    raise ValueError('step')
                return self.send(200, control.plan_step(image, steps, lang, lambda m: ''.join(_app().generate_stream(m, vision=True))))
            if control.clean_action(body.get('action'))['action'] in ('done', 'fail'):
                _app().end_task()
                return self.send(200, {'ok': True})
            control.run_action(body.get('action'))
            return self.send(200, {'ok': True})
        except PermissionError as exc:
            _app().end_task()
            return self.send(409, {'error': 'moved' if str(exc) == 'moved' else 'budget'})
        except (ValueError, TypeError):
            return self.send(400, {'error': 'Некорректный запрос.'})
        except RuntimeError as exc:
            _app().end_task()
            return self.send(502, {'error': str(exc)})

    def handle_provider(self):
        """Settings: which network she thinks with. A key goes in, is checked and stored encrypted; the page only ever gets its last four characters back."""
        op = self.path[len('/provider/'):]
        try:
            body = self.read_json(2000)
            pid = body.get('id') if isinstance(body.get('id'), str) else ''
            if op == 'state':
                return self.send(200, providers.state())
            if op == 'key':
                warn = providers.set_key(pid, body.get('key'))
                audit.log('key.set', providers.CLOUD[pid]['name'])
                _app().start_study()
                return self.send(200, dict(providers.state(), warn=warn))
            if op == 'clear':
                providers.clear_key(pid)
                audit.log('key.clear', (providers.CLOUD.get(pid) or {}).get('name', pid))
                return self.send(200, providers.state())
            if op == 'select':
                providers.select(pid)
                audit.log('provider', (providers.CLOUD.get(pid) or providers.LOCAL.get(pid))['name'])
                _app().start_study()
                return self.send(200, providers.state())
            if op == 'model':
                providers.set_model(pid, body.get('model'))
                return self.send(200, providers.state())
            if op == 'models':
                return self.send(200, {'models': providers.models(pid)})
            if op == 'dismiss':
                providers.dismiss(pid)
                return self.send(200, providers.state())
            return self.send(404, {'error': 'Not found'})
        except providers.ProviderError as exc:
            return self.send(409, {'error': str(exc)})
        except (ValueError, TypeError, AttributeError):
            return self.send(400, {'error': 'Некорректный запрос.'})

    def handle_nook(self):
        """Her corner for the creator's eyes: the list of her notes and the text of one. Read-only."""
        op = self.path[len('/nook/'):]
        try:
            body = self.read_json(2000)
            if op == 'list':
                return self.send(200, {'notes': nook.listing()})
            if op == 'read':
                file = body.get('file')
                if not isinstance(file, str):
                    raise ValueError('file')
                return self.send(200, {'text': nook.read(file)})
            return self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, AttributeError, OSError):
            return self.send(400, {'error': 'Некорректный запрос.'})

    def handle_journal(self):
        """The journal of her hands: list it, take one thing back (where that is possible), or clear it."""
        op = self.path[len('/journal/'):]
        try:
            body = self.read_json(2000)
            if op == 'list':
                return self.send(200, {'entries': audit.listing()})
            if op == 'undo':
                eid = body.get('id')
                if not isinstance(eid, int) or isinstance(eid, bool):
                    raise ValueError('id')
                result = audit.undo(eid)
                return self.send(200 if result['ok'] else 409, result if result['ok'] else {'error': 'journal:' + result['error']})
            if op == 'clear':
                audit.clear()
                return self.send(200, {'ok': True})
            return self.send(404, {'error': 'Not found'})
        except (ValueError, TypeError, AttributeError):
            return self.send(400, {'error': 'Некорректный запрос.'})

    def handle_doc(self):
        """The creator pressed Create on a document plate: build the file in the Luna folder (and open it if asked)."""
        try:
            body = self.read_json(2000)
            made = office.make(body.get('token'), body.get('open') is True)
            audit.log('doc', made['name'], True, True, path=Path(made['folder']) / made['name'])
            return self.send(200, dict(made, ok=True))
        except PermissionError:
            return self.send(403, {'error': 'doc:token'})
        except RuntimeError as exc:
            return self.send(409, {'error': 'doc:' + str(exc)})
        except (ValueError, TypeError, OSError):
            return self.send(400, {'error': 'doc:render'})

    def handle_code_edit(self):
        """The creator saw the diff and pressed Apply: change that one file (a backup is kept) and write it to the journal."""
        try:
            done = codeedit.apply(self.read_json(2000).get('token'))
            audit.log('edit', done['name'], True, True, path=done['path'], b=done['backup'], h=done['after'])
            return self.send(200, {'ok': True, 'name': done['name']})
        except PermissionError:
            return self.send(403, {'error': 'edit:token'})
        except RuntimeError as exc:
            return self.send(409, {'error': 'edit:' + str(exc)})
        except (ValueError, TypeError, AttributeError):
            return self.send(400, {'error': 'edit:write'})

    def handle_project_make(self):
        """The creator saw every file and pressed Apply: create the new project in the sandbox and write it to the journal."""
        try:
            done = projects.apply(self.read_json(2000).get('token'))
            audit.log('project', done['name'], True, True, path=done['folder'], b=done['manifest'], h=done['after'])
            return self.send(200, {'ok': True, 'name': done['name'], 'count': done['count'], 'folder': done['folder']})
        except PermissionError:
            return self.send(403, {'error': 'project:token'})
        except RuntimeError as exc:
            return self.send(409, {'error': 'project:' + str(exc)})
        except (ValueError, TypeError, AttributeError):
            return self.send(400, {'error': 'project:write'})

    def handle_project_ws(self):
        """The creator's own list of folders where she may add new files: show it, add a folder or take one away."""
        try:
            body = self.read_json(2000)
            op = body.get('op')
            if op == 'add':
                added = projects.add_workspace(body.get('path'))
                audit.log('wsadd', added['name'], True, False)
            elif op == 'remove':
                if projects.remove_workspace(body.get('name', '')):
                    audit.log('wsdel', str(body.get('name', ''))[:60], True, False)
            elif op != 'list':
                raise ValueError('bad')
            return self.send(200, {'items': [{'name': w['name'], 'path': w['path']} for w in projects.workspaces()]})
        except ValueError as exc:
            return self.send(400, {'error': 'project:' + (str(exc) if str(exc) in ('bad', 'notdir', 'unsafe', 'dup', 'limit') else 'bad')})
        except (TypeError, AttributeError, OSError):
            return self.send(400, {'error': 'project:bad'})

    def handle_code_read(self):
        """The creator agreed to show her one code file she asked for: send its text back to the page."""
        try:
            shown = devtools.read_code(self.read_json().get('token'))
            shown['text'] = security.neutralize(shown.get('text'))   # a file may carry someone else's words: it can not close the frame it is shown in
            audit.log('read', shown.get('name', ''))
            self.send(200, shown)
        except PermissionError:
            self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})
        except OSError:
            self.send(500, {'error': 'Этот файл нельзя прочитать.'})

    def handle_env(self):
        """The creator agreed to the diagnostics: read-only facts about this computer go back to the page."""
        try:
            shown = envdiag.run(self.read_json().get('token'))
            audit.log('env', shown['name'])
            self.send(200, shown)
        except PermissionError:
            self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})

    def handle_code_scan(self):
        """The creator agreed to the audit of the project: the program measures it and the report goes back to the page."""
        try:
            shown = codescan.run(self.read_json().get('token'))
            audit.log('scan', shown['name'])
            self.send(200, shown)
        except PermissionError:
            self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})
        except OSError:
            self.send(500, {'error': 'Эту папку нельзя просмотреть.'})

    def handle_sql(self):
        """The creator pressed Run: the one read-only query goes to the SQLite file, a few rows come back to the page."""
        try:
            shown = sqlrun.run(self.read_json().get('token'))
            audit.log('sql', shown['db'])
            self.send(200, shown)
        except PermissionError:
            self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
        except RuntimeError as exc:
            code = str(exc)
            self.send(422, {'error': 'badquery' if code.startswith('badquery') else code if code in ('timeout', 'failed') else 'failed', 'detail': code[9:] if code.startswith('badquery:') else ''})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})

    def handle_git_diff(self):
        """The creator agreed to the review of the changes: read-only git runs, the program analyses the diff, the report goes to the page."""
        try:
            shown = gitdiff.run(self.read_json().get('token'))
            shown['text'] = security.neutralize(shown.get('text'))
            audit.log('diff', shown['name'])
            self.send(200, shown)
        except PermissionError:
            self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
        except RuntimeError as exc:
            self.send(422, {'error': str(exc) if str(exc) in ('norepo', 'badref', 'empty', 'nogit') else 'failed'})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})

    def handle_doc_read(self):
        """The creator agreed to show her one of his documents (or the list of a folder): send its text back to the page."""
        try:
            shown = docfiles.read(self.read_json().get('token'))
            shown['text'] = security.neutralize(shown.get('text'))
            audit.log('docread', shown['name'])
            self.send(200, shown)
        except PermissionError:
            self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
        except RuntimeError as exc:
            self.send(501, {'error': str(exc)})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'type'})
        except OSError:
            self.send(500, {'error': 'file'})

    def handle_doc_move(self):
        """The creator pressed Move on the plate: put that one file into that folder, write it to the journal (it can be taken back)."""
        try:
            done = docfiles.move(self.read_json().get('token'))
            audit.log('move', done['name'], True, True, path=done['new'], b=done['old'])
            self.send(200, {'ok': True, 'name': done['name']})
        except PermissionError:
            self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})
        except OSError:
            self.send(500, {'error': 'Не удалось перенести файл.'})

    def handle_run(self, again=False):
        """The creator pressed Run on the plate: run exactly that command in that folder and send the output back to the page."""
        try:
            entry = runner.again() if again else runner.take(self.read_json().get('token'))
            if not entry:
                return self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
            result = runner.run(entry)
            audit.log('run', result['cmd'], result['ok'])
            self.send(200, result)
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})

    def handle_unreal(self):
        """The creator pressed the plate: run exactly the one validated Unreal operation she asked for."""
        try:
            op = unreal_bridge.take(self.read_json().get('token'))
            if not op:
                return self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
            result = unreal_bridge.run(op)
            audit.log('unreal', unreal_bridge.describe(op), result['ok'], undo=True)
            print('Unreal:', op['op'], 'ok' if result['ok'] else result['error'])
            self.send(200, result)
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})

    def handle_godot(self):
        """The creator pressed the plate: run exactly the one validated Godot operation she asked for."""
        try:
            op = godot_bridge.take(self.read_json().get('token'))
            if not op:
                return self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
            result = godot_bridge.run(op)
            audit.log('godot', godot_bridge.describe(op), result['ok'])
            print('Godot:', op['op'], 'ok' if result['ok'] else result['error'])
            self.send(200, result)
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})

    def handle_unity(self):
        """The creator pressed the plate: run exactly the one validated Unity operation she asked for."""
        try:
            op = unity_bridge.take(self.read_json().get('token'))
            if not op:
                return self.send(403, {'error': 'Это действие не запрошено или уже устарело.'})
            result = unity_bridge.run(op)
            audit.log('unity', unity_bridge.describe(op), result['ok'])
            print('Unity:', op['op'], 'ok' if result['ok'] else result['error'])
            self.send(200, result)
        except (ValueError, TypeError, AttributeError):
            self.send(400, {'error': 'Некорректный запрос.'})

    def handle_studio(self):
        """The song library: list, add (the audio itself as the body, its name in X-Name), file (the audio back), info, remove."""
        try:
            op = self.path[len('/studio/'):]
            if op == 'add':
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= studio.MAX_BYTES:
                    return self.send(413, {'error': 'size'})
                name = unquote(self.headers.get('X-Name', ''))[:200]
                entry = studio.add(name, self.rfile.read(size), her=self.headers.get('X-Her') == '1')
                return self.send(200, {'song': entry, 'songs': studio.load()})
            body = self.read_json(2000) if int(self.headers.get('Content-Length', '0')) else {}
            if op == 'list':
                return self.send(200, {'songs': studio.load()})
            sid = body.get('id') if isinstance(body, dict) else None
            if op == 'file':
                found = studio.path(sid)
                if not found:
                    return self.send(404, {'error': 'Not found'})
                info = studio.get(sid)
                hearing.mute(max(60, info.get('secs', 0)) + 8)   # the song comes out of the speakers: it must not count as heard
                kind = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.flac': 'audio/flac', '.m4a': 'audio/mp4'}.get(found.suffix, 'application/octet-stream')
                return self.send(200, found.read_bytes(), kind)
            if op == 'info':
                info = studio.set_info(sid, body.get('bpm'), body.get('secs'))
                return self.send(200, {'song': info}) if info else self.send(404, {'error': 'Not found'})
            if op == 'rename':
                info = studio.rename(sid, body.get('title', ''))
                return self.send(200, {'song': info, 'songs': studio.load()}) if info else self.send(404, {'error': 'Not found'})
            if op == 'remove':
                if not studio.remove(sid):
                    return self.send(404, {'error': 'Not found'})
                return self.send(200, {'songs': studio.load()})
            return self.send(404, {'error': 'Not found'})
        except ValueError as exc:
            code = {'size': 413, 'format': 415, 'full': 409}.get(str(exc), 400)
            return self.send(code, {'error': str(exc)})
        except (TypeError, OSError):
            return self.send(400, {'error': 'Некорректный запрос.'})
