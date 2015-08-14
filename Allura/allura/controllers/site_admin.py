#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import re
import logging
from datetime import datetime, timedelta

from tg import expose, validate, flash, config, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
import bson
import tg
from paste.deploy.converters import aslist
from pylons import app_globals as g
from pylons import tmpl_context as c
from pylons import request
from formencode import validators, Invalid
from webob.exc import HTTPNotFound, HTTPFound

from allura.app import SitemapEntry
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.decorators import require_post
from allura.lib.plugin import SiteAdminExtension, ProjectRegistrationProvider, AuthenticationProvider
from allura.lib import search
from allura.lib.security import require_access, Credentials
from allura.lib.widgets import form_fields as ffw
from allura.ext.admin.widgets import AuditLog
from allura.lib.widgets import forms
from allura import model as M
from allura.command.show_models import dfs, build_model_inheritance_graph
import allura

from urlparse import urlparse


log = logging.getLogger(__name__)


class W:
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    audit = AuditLog()
    admin_search_form = forms.AdminSearchForm


class SiteAdminController(object):

    def __init__(self):
        self.task_manager = TaskManagerController()
        c.site_admin_sidebar_menu = self.sidebar_menu()
        self.user = AdminUserDetailsController()

    def _check_security(self):
        with h.push_context(config.get('site_admin_project', 'allura'),
                            neighborhood=config.get('site_admin_project_nbhd', 'Projects')):
            require_access(c.project, 'admin')

    @expose()
    def _lookup(self, name, *remainder):
        for ep_name in sorted(g.entry_points['site_admin'].keys()):
            admin_extension = g.entry_points['site_admin'][ep_name]
            controller = admin_extension().controllers.get(name)
            if controller:
                return controller(), remainder
        raise HTTPNotFound, name

    def sidebar_menu(self):
        base_url = '/nf/admin/'
        links = [
            SitemapEntry('Home', base_url, ui_icon=g.icons['admin']),
            SitemapEntry('Add Subscribers', base_url + 'add_subscribers', ui_icon=g.icons['admin']),
            SitemapEntry('New Projects', base_url + 'new_projects', ui_icon=g.icons['admin']),
            SitemapEntry('Reclone Repo', base_url + 'reclone_repo', ui_icon=g.icons['admin']),
            SitemapEntry('Task Manager', base_url + 'task_manager?state=busy', ui_icon=g.icons['stats']),
            SitemapEntry('Search Projects', base_url + 'search_projects', ui_icon=g.icons['search']),
            SitemapEntry('Search Users', base_url + 'search_users', ui_icon=g.icons['search']),
        ]
        for ep_name in sorted(g.entry_points['site_admin']):
            g.entry_points['site_admin'][ep_name]().update_sidebar_menu(links)
        return links

    @expose('jinja:allura:templates/site_admin_index.html')
    @with_trailing_slash
    def index(self):
        return {}

    def subscribe_artifact(self, url, user):
        artifact_url = urlparse(url).path[1:-1].split("/")
        neighborhood = M.Neighborhood.query.find({
            "url_prefix": "/" + artifact_url[0] + "/"}).first()

        if artifact_url[0] == "u":
            project = M.Project.query.find({
                "shortname": artifact_url[0] + "/" + artifact_url[1],
                "neighborhood_id": neighborhood._id}).first()
        else:
            project = M.Project.query.find({
                "shortname": artifact_url[1],
                "neighborhood_id": neighborhood._id}).first()

        appconf = M.AppConfig.query.find({
            "options.mount_point": artifact_url[2],
            "project_id": project._id}).first()

        if appconf.url() == urlparse(url).path:
            M.Mailbox.subscribe(
                user_id=user._id,
                app_config_id=appconf._id,
                project_id=project._id)
            return True

        tool_packages = h.get_tool_packages(appconf.tool_name)
        classes = set()
        for depth, cls in dfs(M.Artifact, build_model_inheritance_graph()):
            for pkg in tool_packages:
                if cls.__module__.startswith(pkg + '.'):
                    classes.add(cls)
        for cls in classes:
            for artifact in cls.query.find({"app_config_id": appconf._id}):
                if artifact.url() == urlparse(url).path:
                    M.Mailbox.subscribe(
                        user_id=user._id,
                        app_config_id=appconf._id,
                        project_id=project._id,
                        artifact=artifact)
                    return True
        return False

    @expose('jinja:allura:templates/site_admin_add_subscribers.html')
    @without_trailing_slash
    def add_subscribers(self, **data):
        if request.method == 'POST':
            url = data['artifact_url']
            user = M.User.by_username(data['for_user'])
            if not user or user == M.User.anonymous():
                flash('Invalid login', 'error')
                return data

            try:
                ok = self.subscribe_artifact(url, user)
            except:
                log.warn("Can't subscribe to artifact", exc_info=True)
                ok = False

            if ok:
                flash('User successfully subscribed to the artifact')
                return {}
            else:
                flash('Artifact not found', 'error')

        return data

    @expose('jinja:allura:templates/site_admin_new_projects.html')
    @without_trailing_slash
    def new_projects(self, **kwargs):
        start_dt = kwargs.pop('start-dt', '')
        end_dt = kwargs.pop('end-dt', '')
        try:
            start_dt = datetime.strptime(start_dt, '%Y/%m/%d %H:%M:%S')
        except ValueError:
            start_dt = datetime.utcnow() + timedelta(days=1)
        try:
            end_dt = datetime.strptime(end_dt, '%Y/%m/%d %H:%M:%S')
        except ValueError:
            end_dt = start_dt - timedelta(days=3) if not end_dt else end_dt
        start = bson.ObjectId.from_datetime(start_dt)
        end = bson.ObjectId.from_datetime(end_dt)
        nb = M.Neighborhood.query.get(name='Users')
        projects = (M.Project.query.find({
            'neighborhood_id': {'$ne': nb._id},
            'deleted': False,
            '_id': {'$lt': start, '$gt': end},
        }).sort('_id', -1)).all()
        # pre-populate roles cache, so we won't query mongo for roles for every project
        # when getting admins with p.admins() in a template
        Credentials.get().load_project_roles(*[p._id for p in projects])
        step = start_dt - end_dt
        params = request.params.copy()
        params['start-dt'] = (start_dt + step).strftime('%Y/%m/%d %H:%M:%S')
        params['end-dt'] = (end_dt + step).strftime('%Y/%m/%d %H:%M:%S')
        newer_url = tg.url(params=params).lstrip('/')
        params['start-dt'] = (start_dt - step).strftime('%Y/%m/%d %H:%M:%S')
        params['end-dt'] = (end_dt - step).strftime('%Y/%m/%d %H:%M:%S')
        older_url = tg.url(params=params).lstrip('/')
        return {
            'projects': projects,
            'newer_url': newer_url,
            'older_url': older_url,
            'window_start': start_dt,
            'window_end': end_dt,
        }

    @expose('jinja:allura:templates/site_admin_reclone_repo.html')
    @without_trailing_slash
    @validate(dict(prefix=validators.NotEmpty(),
                   shortname=validators.NotEmpty(),
                   mount_point=validators.NotEmpty()))
    def reclone_repo(self, prefix=None, shortname=None, mount_point=None, **data):
        if request.method == 'POST':
            if c.form_errors:
                error_msg = 'Error: '
                for msg in list(c.form_errors):
                    names = {'prefix': 'Neighborhood prefix', 'shortname':
                             'Project shortname', 'mount_point': 'Repository mount point'}
                    error_msg += '%s: %s ' % (names[msg], c.form_errors[msg])
                    flash(error_msg, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            nbhd = M.Neighborhood.query.get(url_prefix='/%s/' % prefix)
            if not nbhd:
                flash('Neighborhood with prefix %s not found' %
                      prefix, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            c.project = M.Project.query.get(
                shortname=shortname, neighborhood_id=nbhd._id)
            if not c.project:
                flash(
                    'Project with shortname %s not found in neighborhood %s' %
                    (shortname, nbhd.name), 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            c.app = c.project.app_instance(mount_point)
            if not c.app:
                flash('Mount point %s not found on project %s' %
                      (mount_point, c.project.shortname), 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            source_url = c.app.config.options.get('init_from_url')
            source_path = c.app.config.options.get('init_from_path')
            if not (source_url or source_path):
                flash('%s does not appear to be a cloned repo' %
                      c.app, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            allura.tasks.repo_tasks.reclone_repo.post(
                prefix=prefix, shortname=shortname, mount_point=mount_point)
            flash('Repository is being recloned')
        else:
            prefix = 'p'
            shortname = ''
            mount_point = ''
        return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)

    def _search(self, model, fields, add_fields, q=None, f=None, page=0, limit=None, **kw):
        all_fields = fields + [(fld, fld) for fld in add_fields]
        c.search_form = W.admin_search_form(all_fields)
        c.page_list = W.page_list
        c.page_size = W.page_size
        count = 0
        objects = []
        limit, page, start = g.handle_paging(limit, page, default=25)
        if q:
            match = search.site_admin_search(model, q, f, rows=limit, start=start)
            if match:
                count = match.hits
                objects = match.docs
                ids = [obj['id'].split('#')[1] for obj in objects]
                ids = [bson.ObjectId(_id) for _id in ids if _id != 'None']
                mongo_objects = {}
                for obj in model.query.find({'_id': {'$in': ids}}):
                    mongo_objects[str(obj._id)] = obj

                for i in range(len(objects)):
                    obj = objects[i]
                    _id = obj['id'].split('#')[1]
                    obj['object'] = mongo_objects.get(_id)
                # Some objects can be deleted, but still have index in solr, should skip those
                objects = [o for o in objects if o.get('object')]

        def convert_fields(obj):
            # throw the type away (e.g. '_s' from 'url_s')
            result = {}
            for k,val in obj.iteritems():
                name = k.rsplit('_', 1)
                if len(name) == 2:
                    name = name[0]
                else:
                    name = k
                result[name] = val
            return result

        return {
            'q': q,
            'f': f,
            'objects': map(convert_fields, objects),
            'count': count,
            'page': page,
            'limit': limit,
            'fields': fields,
            'additional_fields': add_fields,
            'type_s': model.type_s,
        }

    @without_trailing_slash
    @expose('jinja:allura:templates/site_admin_search.html')
    @validate(validators=dict(q=validators.UnicodeString(if_empty=None),
                              limit=validators.Int(if_invalid=None),
                              page=validators.Int(if_empty=0, if_invalid=0)))
    def search_projects(self, q=None, f=None, page=0, limit=None, **kw):
        fields = [('shortname', 'shortname'), ('name', 'full name')]
        add_fields = aslist(tg.config.get('search.project.additional_search_fields'), ',')
        r = self._search(M.Project, fields, add_fields, q, f, page, limit, **kw)
        r['search_results_template'] = 'allura:templates/site_admin_search_projects_results.html'
        r['additional_display_fields'] = \
            aslist(tg.config.get('search.project.additional_display_fields'), ',')
        r['provider'] = ProjectRegistrationProvider.get()
        return r

    @without_trailing_slash
    @expose('jinja:allura:templates/site_admin_search.html')
    @validate(validators=dict(q=validators.UnicodeString(if_empty=None),
                              limit=validators.Int(if_invalid=None),
                              page=validators.Int(if_empty=0, if_invalid=0)))
    def search_users(self, q=None, f=None, page=0, limit=None, **kw):
        fields = [('username', 'username'), ('display_name', 'display name')]
        add_fields = aslist(tg.config.get('search.user.additional_search_fields'), ',')
        r = self._search(M.User, fields, add_fields, q, f, page, limit, **kw)
        r['objects'] = [dict(u, status=h.get_user_status(u['object'])) for u in r['objects']]
        r['search_results_template'] = 'allura:templates/site_admin_search_users_results.html'
        r['additional_display_fields'] = \
            aslist(tg.config.get('search.user.additional_display_fields'), ',')
        r['provider'] = AuthenticationProvider.get(request)
        return r


class TaskManagerController(object):

    def _check_security(self):
        with h.push_context(config.get('site_admin_project', 'allura'),
                            neighborhood=config.get('site_admin_project_nbhd', 'Projects')):
            require_access(c.project, 'admin')

    @expose('jinja:allura:templates/site_admin_task_list.html')
    @without_trailing_slash
    def index(self, page_num=1, minutes=10, state=None, task_name=None, host=None):
        now = datetime.utcnow()
        try:
            page_num = int(page_num)
        except ValueError:
            page_num = 1
        try:
            minutes = int(minutes)
        except ValueError:
            minutes = 1
        start_dt = now - timedelta(minutes=(page_num - 1) * minutes)
        end_dt = now - timedelta(minutes=page_num * minutes)
        start = bson.ObjectId.from_datetime(start_dt)
        end = bson.ObjectId.from_datetime(end_dt)
        query = {'_id': {'$gt': end}}
        if page_num > 1:
            query['_id']['$lt'] = start
        if state:
            query['state'] = state
        if task_name:
            query['task_name'] = re.compile(re.escape(task_name))
        if host:
            query['process'] = re.compile(re.escape(host))

        tasks = list(M.monq_model.MonQTask.query.find(query).sort('_id', -1))
        for task in tasks:
            task.project = M.Project.query.get(_id=task.context.project_id)
            task.user = M.User.query.get(_id=task.context.user_id)
        newer_url = tg.url(
            params=dict(request.params, page_num=page_num - 1)).lstrip('/')
        older_url = tg.url(
            params=dict(request.params, page_num=page_num + 1)).lstrip('/')
        return dict(
            tasks=tasks,
            page_num=page_num,
            minutes=minutes,
            newer_url=newer_url,
            older_url=older_url,
            window_start=start_dt,
            window_end=end_dt,
        )

    @expose('jinja:allura:templates/site_admin_task_view.html')
    @without_trailing_slash
    def view(self, task_id):
        try:
            task = M.monq_model.MonQTask.query.get(_id=bson.ObjectId(task_id))
        except bson.errors.InvalidId:
            task = None
        if task:
            task.project = M.Project.query.get(_id=task.context.project_id)
            task.app_config = M.AppConfig.query.get(
                _id=task.context.app_config_id)
            task.user = M.User.query.get(_id=task.context.user_id)
        return dict(task=task)

    @expose('jinja:allura:templates/site_admin_task_new.html')
    @without_trailing_slash
    def new(self, **kw):
        """Render the New Task form"""
        return dict(
            form_errors=c.form_errors or {},
            form_values=c.form_values or {},
        )

    @expose()
    @require_post()
    @validate(v.CreateTaskSchema(), error_handler=new)
    def create(self, task, task_args=None, user=None, path=None):
        """Post a new task"""
        args = task_args.get("args", ())
        kw = task_args.get("kwargs", {})
        config_dict = path
        if user:
            config_dict['user'] = user
        with h.push_config(c, **config_dict):
            task = task.post(*args, **kw)
        redirect('view/%s' % task._id)

    @expose()
    @require_post()
    def resubmit(self, task_id):
        try:
            task = M.monq_model.MonQTask.query.get(_id=bson.ObjectId(task_id))
        except bson.errors.InvalidId:
            task = None
        if task is None:
            raise HTTPNotFound()
        task.state = 'ready'
        redirect('../view/%s' % task._id)

    @expose('json:')
    def task_doc(self, task_name, **kw):
        """Return a task's docstring"""
        error, doc = None, None
        try:
            task = v.TaskValidator.to_python(task_name)
            doc = task.__doc__ or 'No doc string available'
        except Invalid as e:
            error = str(e)
        return dict(doc=doc, error=error)


class StatsController(object):
    """Show neighborhood stats."""
    @expose('jinja:allura:templates/site_admin_stats.html')
    @with_trailing_slash
    def index(self):
        neighborhoods = []
        for n in M.Neighborhood.query.find():
            project_count = M.Project.query.find(
                dict(neighborhood_id=n._id)).count()
            configured_count = M.Project.query.find(
                dict(neighborhood_id=n._id, database_configured=True)).count()
            neighborhoods.append((n.name, project_count, configured_count))
        neighborhoods.sort(key=lambda n: n[0])
        return dict(neighborhoods=neighborhoods)


class AdminUserDetailsController(object):

    @expose('jinja:allura:templates/site_admin_user_details.html')
    def _default(self, username, limit=25, page=0):
        user = M.User.by_username(username)
        if not user or user.is_anonymous():
            raise HTTPNotFound()
        projects = user.my_projects().all()
        audit_log = self._audit_log(user, limit, page)
        info = {
            'user': user,
            'status': h.get_user_status(user),
            'projects': projects,
            'audit_log': audit_log,
        }
        p = AuthenticationProvider.get(request)
        info.update(p.user_details(user))
        return info

    def _audit_log(self, user, limit, page):
        limit = int(limit)
        page = int(page)
        if user is None or user.is_anonymous():
            return dict(
                entries=[],
                imit=limit,
                page=page,
                count=0)
        q = M.AuditLog.for_user(user)
        count = q.count()
        q = q.sort('timestamp', -1)
        q = q.skip(page * limit)
        if count > limit:
            q = q.limit(limit)
        else:
            limit = count
        c.audit_log_widget = W.audit
        return dict(
            entries=q.all(),
            limit=limit,
            page=page,
            count=count)

    @expose()
    @require_post()
    def add_audit_trail_entry(self, **kw):
        username = kw.get('username')
        comment = kw.get('comment')
        user = M.User.by_username(username)
        if user and not user.is_anonymous() and comment:
            M.AuditLog.comment_user(c.user, comment, user=user)
            flash('Comment added', 'ok')
        else:
            flash('Can not add comment "%s" for user %s' % (comment, user))
        redirect(request.referer)

    @expose()
    @require_post()
    def set_status(self, username=None, status=None):
        user = M.User.by_username(username)
        if not user or user.is_anonymous():
            raise HTTPNotFound()
        if status == 'enable' and (user.disabled or user.pending):
            AuthenticationProvider.get(request).activate_user(user, audit=False)
            AuthenticationProvider.get(request).enable_user(user)
            flash('User enabled')
        elif status == 'disable' and not user.disabled:
            AuthenticationProvider.get(request).disable_user(user)
            flash('User disabled')
        elif status == 'pending':
            AuthenticationProvider.get(request).deactivate_user(user)
            AuthenticationProvider.get(request).enable_user(user, audit=False)
            flash('Set user status to pending')
        redirect(request.referer)

    @expose()
    @require_post()
    def set_random_password(self, username=None):
        user = M.User.by_username(username)
        if not user or user.is_anonymous():
            raise HTTPNotFound()
        pwd = h.random_password()
        AuthenticationProvider.get(request).set_password(user, None, pwd)
        h.auditlog_user('Set random password', user=user)
        flash('Password is set', 'ok')
        redirect(request.referer)

    @expose()
    @require_post()
    def send_password_reset_link(self, username=None):
        user = M.User.by_username(username)
        if not user or user.is_anonymous():
            raise HTTPNotFound()
        email = user.get_pref('email_address')
        try:
            allura.controllers.auth.AuthController().password_recovery_hash(email)
        except HTTPFound:
            pass  # catch redirect to '/'
        redirect(request.referer)

    @h.vardec
    @expose()
    @require_post()
    def update_emails(self, username, **kw):
        user = M.User.by_username(username)
        if not user or user.is_anonymous():
            raise HTTPNotFound()
        allura.controllers.auth.PreferencesController()._update_emails(user, admin=True, form_params=kw)
        redirect(request.referer)


class StatsSiteAdminExtension(SiteAdminExtension):
    controllers = {'stats': StatsController}

    def update_sidebar_menu(self, links):
        links.append(SitemapEntry('Stats', '/nf/admin/stats',
            ui_icon=g.icons['stats']))
