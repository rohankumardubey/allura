# coding: utf-8

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

import json
import re
import os
import shutil
import tempfile

from datadiff.tools import assert_equal as dd_assert_equal
from nose.tools import assert_equal, assert_in, assert_not_in, assert_not_equal, assert_less
import tg
import pkg_resources
from nose.tools import assert_regexp_matches
from tg import tmpl_context as c
from ming.orm import ThreadLocalORMSession
from mock import patch, PropertyMock

from alluratest.controller import setup_global_objects
from allura import model as M
from allura.lib import helpers as h
from allura.lib import macro
from alluratest.controller import TestController, TestRestApiBase
from allura.tests.decorators import with_tool
from forgegit.tests import with_git
from forgegit import model as GM


class _TestCase(TestController):
    def setUp(self):
        super(_TestCase, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename('forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testgit.git'
        ThreadLocalORMSession.flush_all()
        # ThreadLocalORMSession.close_all()
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.refresh()
        if os.path.isdir(c.app.repo.tarball_path):
            shutil.rmtree(c.app.repo.tarball_path)
        ThreadLocalORMSession.flush_all()
        # ThreadLocalORMSession.close_all()

    @with_tool('test', 'Git', 'testgit-index', 'Git', type='git')
    def setup_testgit_index_repo(self):
        h.set_context('test', 'testgit-index', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename('forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testgit_index.git'
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'testgit-index', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()


class TestUIController(TestController):
    def setUp(self):
        super(TestUIController, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename('forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.name = 'testui2.git'
        c.app.repo.status = 'ready'
        self.repo = c.app.repo
        self.repo.refresh()
        self.rev = self.repo.commit('HEAD')
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()

    def test_repo_loading(self):
        resp = self.app.get('/src-git/').follow().follow()
        assert '<a href="/p/test/src-git/ci/e0d7765883017040d53f9ca9c528940a4dd311c6/">' in resp

    def test_status_html(self):
        resp = self.app.get('/src-git/ci/e0d7765883017040d53f9ca9c528940a4dd311c6/')
        sortedCommits = resp.html.findAll('td')
        actualCommit = ['added', 'aaa.txt', 'removed', 'bbb.txt', 'changed', 'ccc.txt', 'removed', 'ddd.txt', 'added', 'eee.txt', 'added', 'ggg.txt']
        for i, item in enumerate(sortedCommits):
            assert_equal(actualCommit[i], ''.join(item.findAll(text=True)).strip())

class TestRootController(_TestCase):
    @with_tool('test', 'Git', 'weird-chars', 'WeirdChars', type='git')
    def _setup_weird_chars_repo(self):
        h.set_context('test', 'weird-chars', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename('forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'weird-chars.git'
        ThreadLocalORMSession.flush_all()
        c.app.repo.refresh()

    def test_status(self):
        resp = self.app.get('/src-git/status')
        d = json.loads(resp.body)
        assert d == dict(status='ready')

    def test_status_html(self):
        resp = self.app.get('/src-git/').follow().follow()
        # repo status not displayed if 'ready'
        assert None == resp.html.find('div', dict(id='repo_status'))
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.status = 'analyzing'
        ThreadLocalORMSession.flush_all()
        ThreadLocalORMSession.close_all()
        # repo status displayed if not 'ready'
        resp = self.app.get('/src-git/').follow().follow()
        div = resp.html.find('div', dict(id='repo_status'))
        assert div.span.text == 'analyzing'

    def test_index(self):
        resp = self.app.get('/src-git/').follow().follow()
        assert 'git clone /srv/git' in resp

    def test_index_empty(self):
        self.app.get('/git/')

    def test_commit_browser(self):
        self.app.get('/src-git/commit_browser')

    def test_commit_browser_data(self):
        resp = self.app.get('/src-git/commit_browser_data')
        data = json.loads(resp.body)
        assert_equal(
            data['built_tree']['df30427c488aeab84b2352bdf88a3b19223f9d7a'],
            {u'url': u'/p/test/src-git/ci/df30427c488aeab84b2352bdf88a3b19223f9d7a/',
             u'oid': u'df30427c488aeab84b2352bdf88a3b19223f9d7a',
             u'short_id': u'[df3042]',
             u'parents': [u'6a45885ae7347f1cac5103b0050cc1be6a1496c8'],
             u'message': u'Add README', u'row': 2})

    def test_log(self):
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/')
        assert 'Initial commit' in resp
        assert '<div class="markdown_content"><p>Change README</div>' in resp
        assert 'tree/README?format=raw">Download</a>' not in resp
        assert 'Tree' in resp.html.findAll('td')[2].text, resp.html.findAll('td')[2].text
        assert 'byRick Copeland' in resp.html.findAll('td')[0].text, resp.html.findAll('td')[0].text
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/README')
        assert 'View' in resp.html.findAll('td')[2].text
        assert 'Change README' in resp
        assert 'tree/README?format=raw">Download</a>' in resp
        assert 'Add README' in resp
        assert "Initial commit " not in resp
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/a/b/c/')
        assert 'Remove file' in resp
        assert 'Initial commit' in resp
        assert 'Add README' not in resp
        assert 'Change README' not in resp
        resp = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/not/exist')
        assert 'No (more) commits' in resp

    def test_diff_ui(self):
        r = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/?path=/README')
        assert '<div class="grid-19"><input type="button" value="Compare" class="compare_revision"></div>' in r
        assert '<input type="checkbox" class="revision"' in r
        assert 'revision="1e146e67985dcd71c74de79613719bef7bddca4a"' in r
        assert 'url_commit="/p/test/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/">' in r

        r = self.app.get('/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/log/')
        assert '<div class="grid-19"><input type="button" value="Compare" class="compare_revision"></div>' not in r
        assert '<input type="checkbox" class="revision"' not in r
        assert 'revision="1e146e67985dcd71c74de79613719bef7bddca4a"' not in r
        assert 'url_commit="/p/test/src-git/ci/1e146e67985dcd71c74de79613719bef7bddca4a/">' not in r

    def test_tags(self):
        self.app.get('/src-git/ref/master~/tags/')

    def _get_ci(self, repo='/p/test/src-git/'):
        r = self.app.get(repo + 'ref/master/')
        resp = r.follow()
        for tag in resp.html.findAll('a'):
            if tag['href'].startswith(repo + 'ci/'):
                href = tag['href']
                if href.endswith('tree/'):
                    href = href[:-5]
                return href
        return None

    def test_commit(self):
        ci = self._get_ci()
        resp = self.app.get(ci)
        assert 'Rick' in resp, resp.showbrowser()

    def test_feed(self):
        for ext in ['', '.rss']:
            r = self.app.get('/src-git/feed%s' % ext)
            channel = r.xml.find('channel')
            title = channel.find('title').text
            assert_equal(title, 'test Git changes')
            description = channel.find('description').text
            assert_equal(description,
                         'Recent changes to Git repository in test project')
            link = channel.find('link').text
            assert_equal(link, 'http://localhost/p/test/src-git/')
            earliest_commit = channel.findall('item')[-1]
            assert_equal(earliest_commit.find('title').text, 'Initial commit')
            link = 'http://localhost/p/test/src-git/ci/9a7df788cf800241e3bb5a849c8870f2f8259d98/'
            assert_equal(earliest_commit.find('link').text, link)
            assert_equal(earliest_commit.find('guid').text, link)

        # .atom has slightly different structure
        prefix = '{http://www.w3.org/2005/Atom}'
        r = self.app.get('/src-git/feed.atom')
        title = r.xml.find(prefix + 'title').text
        assert_equal(title, 'test Git changes')
        link = r.xml.find(prefix + 'link').attrib['href']
        assert_equal(link, 'http://localhost/p/test/src-git/')
        earliest_commit = r.xml.findall(prefix + 'entry')[-1]
        assert_equal(earliest_commit.find(prefix + 'title').text, 'Initial commit')
        link = 'http://localhost/p/test/src-git/ci/9a7df788cf800241e3bb5a849c8870f2f8259d98/'
        assert_equal(earliest_commit.find(prefix + 'link').attrib['href'], link)

    def test_tree(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert len(resp.html.findAll('tr')) == 2, resp.showbrowser()
        resp = self.app.get(ci + 'tree/')
        assert 'README' in resp, resp.showbrowser()
        links = [a.get('href') for a in resp.html.findAll('a')]
        assert 'README' in links, resp.showbrowser()
        assert 'README/' not in links, resp.showbrowser()

    def test_tree_extra_params(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/?format=raw')
        assert 'README' in resp, resp.showbrowser()

    def test_tree_invalid(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/foo', status=404)
        resp = self.app.get(ci + 'tree/foo/bar', status=404)

    def test_file(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README')
        assert 'README' in resp.html.find('h2', {'class': 'dark title'}).contents[4]
        content = str(resp.html.find('div', {'class': 'clip grid-19 codebrowser'}))
        assert 'This is readme' in content, content
        assert '<span id="l1" class="code_block">' in resp
        assert 'var hash = window.location.hash.substring(1);' in resp

    def test_file_raw(self):
        self._setup_weird_chars_repo()
        ci = self._get_ci(repo='/p/test/weird-chars/')
        url = ci + 'tree/' + h.urlquote(u'привіт.txt') + '?format=raw'
        resp = self.app.get(url)
        assert_in(u'Привіт!\nWhich means Hello!', resp.body.decode('utf-8'))
        assert_equal(resp.headers.get('Content-Disposition').decode('utf-8'),
                     u'attachment;filename="привіт.txt"')

        url = ci + 'tree/' + h.urlquote(u'with space.txt') + '?format=raw'
        resp = self.app.get(url)
        assert_in(u'with space', resp.body.decode('utf-8'))
        assert_equal(resp.headers.get('Content-Disposition').decode('utf-8'),
                     u'attachment;filename="with space.txt"')

    def test_invalid_file(self):
        ci = self._get_ci()
        self.app.get(ci + 'tree/READMEz', status=404)

    def test_diff(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README?diff=df30427c488aeab84b2352bdf88a3b19223f9d7a')
        assert 'readme' in resp, resp.showbrowser()
        assert '+++' in resp, resp.showbrowser()

    def test_diff_view_mode(self):
        ci = self._get_ci()
        fn = 'tree/README?diff=df30427c488aeab84b2352bdf88a3b19223f9d7a'
        r = self.app.get(ci + fn + '&diformat=regular')
        assert fn + '&amp;diformat=sidebyside">Switch to side-by-side view</a>' in r

        r = self.app.get(ci + fn + '&diformat=sidebyside')
        assert fn + '&amp;diformat=regular">Switch to unified view</a>' in r
        assert '<table class="side-by-side-diff">' in r

    def test_file_force_display(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/README?force=True')
        content = str(resp.html.find('div', {'class': 'clip grid-19 codebrowser'}))
        assert re.search(r'<pre>.*This is readme', content), content
        assert '</pre>' in content, content

    def test_index_files(self):
        """Test that `index.*` files are viewable in code browser"""
        self.setup_testgit_index_repo()
        ci = '/p/test/testgit-index/ci/eaec8e7fc91f18d6bf294379d16146ef9226a1ab/'

        # `index.html` in repo root
        r = self.app.get(ci + 'tree/index.html')
        header_bit = r.html.find('h2', {'class': 'dark title'}).contents[4]
        assert 'index.html' in header_bit, header_bit
        content = str(r.html.find('div', {'class': 'clip grid-19 codebrowser'}))
        assert ('<span class="p">&lt;</span><span class="nt">h1</span><span class="p">&gt;</span>'
                'index.html'
                ) in content, content

        # `index` dir in repo root
        r = self.app.get(ci + 'tree/index/')
        assert 'inside_index_dir.txt' in r

        # `index.htm` in `index` dir
        r = self.app.get(ci + 'tree/index/index.htm')
        header = r.html.find('h2', {'class': 'dark title'})
        assert 'index' in header.contents[5], header.contents[5]
        assert 'index.htm' in header.contents[6], header.contents[6]
        content = str(r.html.find('div', {'class': 'clip grid-19 codebrowser'}))
        assert ('<span class="p">&lt;</span><span class="nt">h1</span><span class="p">&gt;</span>'
                'index/index.htm'
                ) in content, content

    def test_subscribe(self):
        user = M.User.query.get(username='test-user')
        ci = self._get_ci()

        # user is not subscribed
        assert not M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get(ci + 'tree/',
                         extra_environ={'username': str(user.username)})
        opts = self.subscription_options(r)
        assert_equal(opts['subscribed'], False)

        # subscribe
        r = self.app.post(str(ci + 'tree/subscribe'),
                          {'subscribe': True},
                          extra_environ={'username': str(user.username)})
        assert_equal(r.json, {'status': 'ok', 'subscribed': True})
        # user is subscribed
        assert M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get(ci + 'tree/',
                         extra_environ={'username': str(user.username)})
        opts = self.subscription_options(r)
        assert_equal(opts['subscribed'], True)

        # unsubscribe
        r = self.app.post(str(ci + 'tree/subscribe'),
                          {'unsubscribe': True},
                          extra_environ={'username': str(user.username)})
        assert_equal(r.json, {'status': 'ok', 'subscribed': False})
        # user is not subscribed
        assert not M.Mailbox.subscribed(user_id=user._id)
        r = self.app.get(ci + 'tree/',
                         extra_environ={'username': str(user.username)})
        opts = self.subscription_options(r)
        assert_equal(opts['subscribed'], False)

    def test_timezone(self):
        ci = self._get_ci()
        resp = self.app.get(ci + 'tree/')
        assert "Thu Oct 07, 2010 06:44 PM UTC" in resp, resp.showbrowser()

    def test_checkout_input(self):
        ci = self._get_ci()
        r = self.app.get('/src-git/commit_browser')
        assert not '<div id="access_urls"' in r
        r = self.app.get('/src-git/fork')
        assert not '<div id="access_urls"' in r
        r = self.app.get(ci + 'tree/README?diff=df30427c488aeab84b2352bdf88a3b19223f9d7a')
        assert not '<div id="access_urls"' in r
        r = self.app.get(ci + 'tree/README')
        assert not '<div id="access_urls"' in r
        r = self.app.get(ci + 'tree/')
        assert '<div id="access_urls"' in r

    def test_tarball(self):
        ci = self._get_ci()
        r = self.app.get(ci + 'tree/')
        assert '/p/test/src-git/ci/master/tarball' in r
        assert 'Download Snapshot' in r
        r = self.app.post('/p/test/src-git/ci/master/tarball').follow()
        assert 'Generating snapshot...' in r
        r = self.app.get('/p/test/src-git/ci/master/tarball')
        assert 'Generating snapshot...' in r
        M.MonQTask.run_ready()
        ThreadLocalORMSession.flush_all()
        r = self.app.get(ci + 'tarball_status')
        assert '{"status": "complete"}' in r
        r = self.app.get('/p/test/src-git/ci/master/tarball_status')
        assert '{"status": "complete"}' in r
        r = self.app.get('/p/test/src-git/ci/master/tarball')
        assert 'Your download will begin shortly' in r

    def test_tarball_link_in_subdirs(self):
        '''Go to repo subdir and check 'Download Snapshot' link'''
        self.setup_testgit_index_repo()
        r = self.app.get('/p/test/testgit-index/ci/master/tree/index/')
        form = r.html.find('form', 'tarball')
        assert_equal(form.get('action'), '/p/test/testgit-index/ci/master/tarball')
        assert_equal(form.input.get('value'), '/index')

    def test_default_branch(self):
        assert_equal(c.app.default_branch_name, 'master')
        c.app.repo.set_default_branch('zz')
        assert_equal(c.app.default_branch_name, 'zz')
        c.app.repo.set_default_branch('master')
        assert_equal(c.app.default_branch_name, 'master')

    def test_set_default_branch(self):
        r = self.app.get('/p/test/admin/src-git/set_default_branch_name')
        assert '<input type="text" name="branch_name" id="branch_name"  value="master"/>' in r
        self.app.post('/p/test/admin/src-git/set_default_branch_name',
                      params={'branch_name': 'zz'})
        r = self.app.get('/p/test/admin/src-git/set_default_branch_name')
        assert '<input type="text" name="branch_name" id="branch_name"  value="zz"/>' in r
        r = self.app.get('/p/test/src-git/').follow().follow()
        assert '<span class="scm-branch-label">zz</span>' in r
        # 'bad' is a file name which in zz, but not in master
        assert_in('bad</a>', r)

        self.app.post('/p/test/admin/src-git/set_default_branch_name',
                      params={'branch_name': 'master'})
        r = self.app.get('/p/test/src-git/').follow().follow()
        assert_not_in('bad</a>', r)
        assert_in('README</a>', r)

    def test_set_checkout_url(self):
        r = self.app.get('/p/test/admin/src-git/checkout_url')
        r.form['external_checkout_url'].value = 'http://foo.bar/baz'
        r.form['merge_disabled'].checked = True
        r = r.form.submit()
        assert_equal(json.loads(self.webflash(r))['message'],
                     "External checkout URL successfully changed. One-click merge disabled.")
        # for some reason c.app.config.options has old values still
        app_config = M.AppConfig.query.get(_id=c.app.config._id)
        assert_equal(app_config.options['external_checkout_url'], 'http://foo.bar/baz')
        assert_equal(app_config.options['merge_disabled'], True)

    def test_markdown_syntax_dialog(self):
        r = self.app.get('/p/test/src-git/markdown_syntax_dialog')
        assert_in('<h1>Markdown Syntax Guide</h1>', r)


class TestRestController(_TestCase):
    def test_index(self):
        self.app.get('/rest/p/test/src-git/', status=200)

    def test_commits(self):
        self.app.get('/rest/p/test/src-git/commits', status=200)


class TestHasAccessAPI(TestRestApiBase):
    def setUp(self):
        super(TestHasAccessAPI, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        pass

    def test_has_access_no_params(self):
        self.api_get('/rest/p/test/src-git/has_access', status=404)
        self.api_get('/rest/p/test/src-git/has_access?user=root', status=404)
        self.api_get('/rest/p/test/src-git/has_access?perm=read', status=404)

    def test_has_access_unknown_params(self):
        """Unknown user and/or permission always False for has_access API"""
        r = self.api_get(
            '/rest/p/test/src-git/has_access?user=babadook&perm=read',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)
        r = self.api_get(
            '/rest/p/test/src-git/has_access?user=test-user&perm=jump',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)

    def test_has_access_not_admin(self):
        """
        User which has no 'admin' permission on neighborhood can't use
        has_access API
        """
        self.api_get(
            '/rest/p/test/src-git/has_access?user=test-admin&perm=admin',
            user='test-user',
            status=403)

    def test_has_access(self):
        r = self.api_get(
            '/rest/p/test/src-git/has_access?user=test-admin&perm=create',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], True)
        r = self.api_get(
            '/rest/p/test/src-git/has_access?user=test-user&perm=create',
            user='root')
        assert_equal(r.status_int, 200)
        assert_equal(r.json['result'], False)


class TestFork(_TestCase):
    def setUp(self):
        super(TestFork, self).setUp()
        to_project = M.Project.query.get(
            shortname='test2', neighborhood_id=c.project.neighborhood_id)
        r = self.app.post('/src-git/fork', params=dict(
            project_id=str(to_project._id),
            mount_point='code',
            mount_label='Test forked repository'))
        assert "{status: 'error'}" not in str(r.follow())
        cloned_from = c.app.repo
        with h.push_context('test2', 'code', neighborhood='Projects'):
            c.app.repo.init_as_clone(
                cloned_from.full_fs_path,
                cloned_from.app.config.script_name(),
                cloned_from.full_fs_path)
            # Add commit to a forked repo, thus merge requests will not be empty
            # clone repo to tmp location first (can't add commit to bare repos
            # directly)
            clone_path = tempfile.mkdtemp()
            cloned = c.app.repo._impl._git.clone(clone_path)
            with open(clone_path + '/README', 'w+') as f:
                f.write('Very useful README')
            cloned.index.add(['README'])
            cloned.index.commit('Improve documentation')
            cloned.remotes[0].push()
            c.app.repo.refresh()
            self.forked_repo = c.app.repo
            shutil.rmtree(clone_path, ignore_errors=True)

    def _follow(self, r, **kw):
        if r.status_int == 302:
            print r.request.url
        while r.status_int == 302:
            print ' ==> 302 ==> %s' % r.location
            r = r.follow(**kw)
        return r

    def _upstream_page(self, **kw):
        r = self.app.get('/src-git/', **kw)
        r = self._follow(r, **kw)
        return r

    def _fork_page(self, **kw):
        r = self.app.get('/p/test2/code/', **kw)
        r = self._follow(r, **kw)
        return r

    def _find_request_merge_form(self, resp):
        def cond(f):
            return f.action == 'do_request_merge'
        return self.find_form(resp, cond)

    def _request_merge(self, **kw):
        r = self.app.get('/p/test2/code/request_merge', **kw)
        r = self._follow(r, **kw)
        form = self._find_request_merge_form(r)
        r = form.submit()
        r = self._follow(r, **kw)
        mr_num = r.request.url.split('/')[-2]
        assert mr_num.isdigit(), mr_num
        return r, mr_num

    def test_forks_list(self):
        r = self.app.get('%sforks/' % c.app.repo.url())
        assert 'test2 / code' in r

    def test_fork_form(self):
        r = self.app.get('%sfork/' % c.app.repo.url())
        assert '<input type="text" name="mount_point" value="test"/>' in r
        assert '<input type="text" name="mount_label" value="Test Project - Git"/>' in r, r

    def test_fork_listed_in_parent(self):
        assert 'Forks' in self._upstream_page()

    def test_fork_display(self):
        r = self._fork_page()
        assert 'Clone of' in r
        assert 'Test forked repository' in r

    def test_fork_links_go_to_fork(self):
        r = self._fork_page()
        hrefs = (a.get('href') for a in r.html('a'))
        hrefs = (href for href in hrefs if href and '/ci/' in href)
        for href in hrefs:
            assert href.startswith('/p/test2/code/'), href

    def test_merge_request_visible_to_admin(self):
        assert 'Request Merge' in self._fork_page()

    def test_merge_request_invisible_to_non_admin(self):
        assert 'Request Merge' not in self._fork_page(
            extra_environ=dict(username='test-user'))

    def test_merge_action_available_to_admin(self):
        self.app.get('/p/test2/code/request_merge')

    def test_merge_action_unavailable_to_non_admin(self):
        self.app.get(
            '/p/test2/code/request_merge',
            status=403, extra_environ=dict(username='test-user'))

    def test_merge_request_detail_view(self):
        r, mr_num = self._request_merge()
        assert_in('wants to merge', r)

        merge_instructions = r.html.findAll('textarea')[0].getText()
        assert_in('git checkout master', merge_instructions)
        assert_in('git fetch /srv/git/p/test2/code master', merge_instructions)
        c_id = self.forked_repo.get_heads()[0]['object_id']
        assert_in('git merge {}'.format(c_id), merge_instructions)
        assert_regexp_matches(str(r), r'[0-9]+ seconds? ago')

        merge_form = r.html.find('div', {'class': 'merge-help-text merge-ok'})
        assert merge_form
        assert_in('Merge request has no conflicts. You can merge automatically.', merge_form.getText())

        assert_not_in('Improve documentation', r)  # no details yet

        # a task is busy/ready to compute
        r = self.app.get('/p/test/src-git/merge-requests/1/commits_html', status=202)  # 202 used for "busy"
        # run task to compute the commits list
        task = M.MonQTask.query.get(task_name='allura.tasks.repo_tasks.determine_mr_commits', state='ready')
        task()
        ThreadLocalORMSession.close_all()  # close ming connections so that new data gets loaded later

        def assert_commit_details(r):
            assert_in('Improve documentation', r.body)
            revs = r.html.findAll('tr', attrs={'class': 'rev'})
            assert_equal(len(revs), 1)
            rev_links = revs[0].findAll('a', attrs={'class': 'rev'})
            browse_links = revs[0].findAll('a', attrs={'class': 'browse'})
            assert_equal(rev_links[0].get('href'), '/p/test2/code/ci/%s/' % c_id)
            assert_equal(rev_links[0].getText(), '[%s]' % c_id[:6])
            assert_equal(browse_links[0].get('href'),
                         '/p/test2/code/ci/%s/tree' % c_id)
            assert_equal(browse_links[0].getText(), 'Tree')

        r = self.app.get('/p/test/src-git/merge-requests/1/commits_html', status=200)
        assert_commit_details(r)

        r = self.app.get('/p/test/src-git/merge-requests/1/', status=200)
        assert_commit_details(r)

    def test_merge_request_detail_noslash(self):
        self._request_merge()
        r = self.app.get('/p/test/src-git/merge-requests/1', status=301)
        assert_equal(r.location, 'http://localhost/p/test/src-git/merge-requests/1/')

    def test_merge_request_with_deleted_repo(self):
        self._request_merge()
        h.set_context('test2', 'code', neighborhood='Projects')
        c.app.repo.delete()
        ThreadLocalORMSession.flush_all()

        r = self.app.get('/p/test/src-git/merge-requests/')
        assert '<i>(deleted)</i>' in r

        r = self.app.get('/p/test/src-git/merge-requests/1/')
        assert '''Original repository by
      <a href="/u/test-admin/">Test Admin</a>
      is deleted''' in r, r

    def test_merge_request_list_view(self):
        r, mr_num = self._request_merge()
        r = self.app.get('/p/test/src-git/merge-requests/')
        assert 'href="%s/"' % mr_num in r, r
        assert_regexp_matches(r.html.findAll('span')[-2].getText(), r'[0-9]+ seconds? ago')
        assert_regexp_matches(r.html.findAll('span')[-1].getText(), r'[0-9]+ seconds? ago')

    def test_merge_request_update_status(self):
        r, mr_num = self._request_merge()
        r = self.app.post('/p/test/src-git/merge-requests/%s/save' % mr_num,
                          params=dict(status='rejected')).follow()
        assert 'Merge Request #%s:  (rejected)' % mr_num in r, r

    def test_merge_request_default_branches(self):
        _select_val = lambda r, n: r.html.find('select', {'name': n}).find(selected=True).string
        r = self.app.get('/p/test2/code/request_merge')
        assert_equal(_select_val(r, 'source_branch'), 'master')
        assert_equal(_select_val(r, 'target_branch'), 'master')
        r = self.app.get('/p/test2/code/ci/zz/tree/').click('Request Merge')
        assert_equal(_select_val(r, 'source_branch'), 'zz')
        assert_equal(_select_val(r, 'target_branch'), 'master')
        GM.Repository.query.get(_id=c.app.repo._id).default_branch_name = 'zz'
        ThreadLocalORMSession.flush_all()
        r = self.app.get('/p/test2/code/request_merge')
        assert_equal(_select_val(r, 'source_branch'), 'master')
        assert_equal(_select_val(r, 'target_branch'), 'zz')
        r = self.app.get('/p/test2/code/ci/zz/tree/').click('Request Merge')
        assert_equal(_select_val(r, 'source_branch'), 'zz')
        assert_equal(_select_val(r, 'target_branch'), 'zz')

    def test_merge_request_with_branch(self):
        def get_mr_page(r):
            r = r.follow()  # get merge request page; creates bg task for determining commits
            task = M.MonQTask.query.get(task_name='allura.tasks.repo_tasks.determine_mr_commits', state='ready')
            task()
            ThreadLocalORMSession.close_all()  # close ming connections so that new data gets loaded later
            r = self.app.get(r.request.url)  # refresh, data should be there now
            return r

        r = self.app.post('/p/test2/code/do_request_merge',
                          params={
                              'source_branch': 'zz',
                              'target_branch': 'zz',
                              'summary': 'summary',
                              'description': 'description'})
        r = get_mr_page(r)
        assert '[5c4724]' not in r

        # again with different branch
        r = self.app.post('/p/test2/code/do_request_merge',
                          params={
                              'source_branch': 'zz',
                              'target_branch': 'master',
                              'summary': 'summary',
                              'description': 'description'})
        r = get_mr_page(r)
        assert '[5c4724]' in r, r

    def test_merge_request_edit(self):
        r = self.app.post('/p/test2/code/do_request_merge',
                          params={
                              'source_branch': 'zz',
                              'target_branch': 'master',
                              'summary': 'summary',
                              'description': 'description',
                          }).follow()
        assert '<a class="icon" href="edit" title="Edit"><i class="fa fa-edit"></i>&nbsp;Edit</a>' in r
        r = self.app.get('/p/test/src-git/merge-requests/1/edit')
        assert 'value="summary"' in r
        assert '<option selected value="zz">zz</option>' in r
        md_edit = r.html.find('div', {'class': 'markdown_edit'})
        assert md_edit is not None, 'MarkdownEdit widget not found'

        r = self.app.post('/p/test/src-git/merge-requests/1/do_request_merge_edit',
                          params={
                              'source_branch': 'zz',
                              'target_branch': 'master',
                              'summary': 'changed summary',
                              'description': 'changed description'
                          },
                          extra_environ=dict(username='*anonymous'),
                          status=302,
                          ).follow()
        assert 'Login' in r

        r = self.app.post('/p/test/src-git/merge-requests/1/do_request_merge_edit',
                          params={
                              'source_branch': 'master',
                              'target_branch': 'master',
                              'summary': 'changed summary',
                              'description': 'changed description',
                          }).follow()

        assert '[5c4724]' not in r
        assert '<p>changed description</p' in r
        assert 'Merge Request #1: changed summary (open)' in r
        changes = r.html.findAll('div', attrs={'class': 'markdown_content'})[-1]
        dd_assert_equal(unicode(changes), """
<div class="markdown_content"><ul>
<li>
<p><strong>Summary</strong>: summary --&gt; changed summary</p>
</li>
<li>
<p><strong>Source branch</strong>: zz --&gt; master</p>
</li>
<li>
<p><strong>Description</strong>:</p>
</li>
</ul>
<p>Diff:</p>
<div class="codehilite"><pre><span></span><span class="gd">--- old</span>
<span class="gi">+++ new</span>
<span class="gu">@@ -1 +1 @@</span>
<span class="gd">-description</span>
<span class="gi">+changed description</span>
</pre></div>
</div>
""".strip())

        r = self.app.get('/p/test/src-git/merge-requests').follow()
        assert '<a href="1/">changed summary</a>' in r

    def test_merge_request_get_markdown(self):
        self.app.post('/p/test2/code/do_request_merge',
                          params={
                              'source_branch': 'zz',
                              'target_branch': 'master',
                              'summary': 'summary',
                              'description': 'description',
                          })
        response = self.app.get('/p/test/src-git/merge-requests/1/get_markdown')
        assert 'description' in response

    def test_merge_request_update_markdown(self):
        self.app.post('/p/test2/code/do_request_merge',
                          params={
                              'source_branch': 'zz',
                              'target_branch': 'master',
                              'summary': 'summary',
                              'description': 'description',
                          })
        response = self.app.post(
            '/p/test/src-git/merge-requests/1/update_markdown',
            params={
                'text': '- [x] checkbox'})
        assert response.json['status'] == 'success'
        # anon users can't edit markdown
        response = self.app.post(
            '/p/test/src-git/merge-requests/1/update_markdown',
            params={
                'text': '- [x] checkbox'},
            extra_environ=dict(username='*anonymous'))
        assert response.json['status'] == 'no_permission'

    @patch.object(GM.Repository, 'merge_request_commits', autospec=True)
    def test_merge_request_commits_error(self, mr_commits):
        r, mr_num = self._request_merge()
        mr_commits.side_effect = Exception
        r = self.app.get('/p/test/src-git/merge-requests/%s/' % mr_num)
        # errors don't show up on the page directly any more, so just assert that the bg task is there
        assert_in('commits-loading', r)
        self.app.get('/p/test/src-git/merge-requests/%s/commits_html' % mr_num, status=202)  # 202 used for "busy"

    def test_merge_request_validation_error(self):
        r = self.app.get('/p/test2/code/request_merge')
        r = self._follow(r)
        form = self._find_request_merge_form(r)
        form['source_branch'].options.append(('bogus', False))
        form['source_branch'].value = 'bogus'
        r = form.submit()
        r = self._follow(r)
        r.mustcontain('Value must be one of:')


class TestDiff(TestController):
    def setUp(self):
        super(TestDiff, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename('forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testmime.git'
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()

    def test_diff(self):
        r = self.app.get('/src-git/ci/d961abbbf10341ee18a668c975842c35cfc0bef2/tree/1.png'
                         '?barediff=2ce83a24e52c21e8d2146b1a04a20717c0bb08d7')
        assert 'alt="2ce83a2..."' in r
        assert 'alt="d961abb..."' in r

        r = self.app.get('/src-git/ci/d961abbbf10341ee18a668c975842c35cfc0bef2/tree/1.png'
                         '?diff=2ce83a24e52c21e8d2146b1a04a20717c0bb08d7')
        assert 'alt="2ce83a2..."' in r
        assert 'alt="d961abb..."' in r


class TestGitRename(TestController):
    def setUp(self):
        super(TestGitRename, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename('forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'testrename.git'
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()

    def test_log(self):
        # commit after the rename
        resp = self.app.get('/src-git/ci/259c77dd6ee0e6091d11e429b56c44ccbf1e64a3/log/?path=/f2.txt')
        assert '<b>renamed from</b>' in resp
        assert '/f.txt' in resp
        assert '(27 Bytes)' in resp
        assert '(19 Bytes)' in resp

        # commit before the rename
        resp = self.app.get('/src-git/ci/fbb0644603bb6ecee3ebb62efe8c86efc9b84ee6/log/?path=/f.txt')
        assert '(19 Bytes)' in resp
        assert '(10 Bytes)' in resp

        # first commit, adding the file
        resp = self.app.get('/src-git/ci/7c09182e61af959e4f1fb0e354bab49f14ef810d/tree/f.txt')
        assert "2 lines (1 with data), 10 Bytes" in resp

    @patch.dict(h.tg.config, {'scm.commit.git.detect_copies': 'true'})
    def test_commit(self):
        # get the rename commit itself
        resp = self.app.get('/src-git/ci/b120505a61225e6c14bee3e5b5862db81628c35c/')

        # the top portion of the output
        assert "<td>renamed" in resp
        assert "f.txt -&gt; f2.txt" in resp

        # the diff portion of the output
        resp_no_ws = re.sub(r'\s+', '', str(resp))
        assert_in('<a href="/p/test/src-git/ci/fbb0644603bb6ecee3ebb62efe8c86efc9b84ee6/tree/f.txt">f.txt</a>'
                  'to<a href="/p/test/src-git/ci/b120505a61225e6c14bee3e5b5862db81628c35c/tree/f2.txt">f2.txt</a>'
                  .replace(' ', ''), resp_no_ws)
        assert '<span class="empty-diff">File was renamed.</span>' in resp


class TestGitBranch(TestController):
    def setUp(self):
        super(TestGitBranch, self).setUp()
        self.setup_with_tools()

    @with_git
    def setup_with_tools(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        repo_dir = pkg_resources.resource_filename('forgegit', 'tests/data')
        c.app.repo.fs_path = repo_dir
        c.app.repo.status = 'ready'
        c.app.repo.name = 'test_branch.git'
        ThreadLocalORMSession.flush_all()
        h.set_context('test', 'src-git', neighborhood='Projects')
        c.app.repo.refresh()
        ThreadLocalORMSession.flush_all()

    def test_exotic_default_branch(self):
        r = self.app.get('/src-git/').follow().follow()
        assert 'README</a>' in r
        assert_equal(c.app.repo.get_default_branch('master'), 'test')


class TestIncludeMacro(_TestCase):
    def setUp(self):
        super(TestIncludeMacro, self).setUp()
        setup_global_objects()

    def test_parse_repo(self):
        assert_equal(macro.parse_repo('app'), None)
        assert_equal(macro.parse_repo('proj:app'), None)
        assert_equal(macro.parse_repo('nbhd:test:src-git'), None)
        assert_equal(macro.parse_repo('a:b:c:d:e:f'), None)
        assert_not_equal(macro.parse_repo('src-git'), None)
        assert_not_equal(macro.parse_repo('test:src-git'), None)
        assert_not_equal(macro.parse_repo('p:test:src-git'), None)

    def test_include_file_no_repo(self):
        expected = '[[include repo %s (not found)]]'
        assert_equal(macro.include_file(None), expected % None)
        assert_equal(macro.include_file('a:b'), expected % 'a:b')
        assert_equal(macro.include_file('repo'), expected % 'repo')

    def test_include_file_permissions(self):
        h.set_context('test', 'src-git', neighborhood='Projects')
        role = M.ProjectRole.by_name('*anonymous')._id
        read_perm = M.ACE.allow(role, 'read')
        acl = c.app.config.acl
        if read_perm in acl:
            acl.remove(read_perm)
        c.user = M.User.anonymous()
        expected = "[[include: you don't have a read permission for repo src-git]]"
        assert_equal(macro.include_file('src-git'), expected)

    def test_include_file_cant_find_file(self):
        expected = "[[include can't find file %s in revision %s]]"
        assert_equal(macro.include_file('src-git', 'a.txt'),
                     expected % ('a.txt', '1e146e67985dcd71c74de79613719bef7bddca4a'))
        assert_equal(macro.include_file('src-git', 'a.txt', '6a45885ae7347f1cac5103b0050cc1be6a1496c8'),
                     expected % ('a.txt', '6a45885ae7347f1cac5103b0050cc1be6a1496c8'))

    @patch('allura.model.repo.Blob.has_pypeline_view', new_callable=PropertyMock)
    @patch('allura.model.repo.Blob.has_html_view', new_callable=PropertyMock)
    def test_include_file_cant_display(self, has_html_view, has_pypeline_view):
        has_html_view.return_value = False
        has_pypeline_view.return_value = False
        expected = "[[include can't display file README in revision 1e146e67985dcd71c74de79613719bef7bddca4a]]"
        assert_equal(macro.include_file('src-git', 'README'), expected)

    def test_include_file_display(self):
        result = macro.include_file('src-git', 'README')
        assert_in('This is readme', result)
        assert_in('Another Line', result)
