import re


class GitHubMarkdownConverter(object):

    def __init__(self, gh_user, gh_project):
        self.gh_project = '%s/%s' % (gh_user, gh_project)
        self.gh_base_url = u'https://github.com/'
        self.code_patterns = ['```', '~~~~~']

    def convert(self, text):
        lines = self._parse_lines(text.split('\n'))
        return '\n'.join(lines)

    def _parse_lines(self, lines):
        in_block = False
        new_lines = []
        for line in lines:
            nextline = False
            for p in self.code_patterns:
                if line.startswith(p):
                    if p == '```':
                        syntax = line.lstrip('`').strip()
                        if syntax:
                            new_lines.append(self._codeblock_syntax(syntax))
                    in_block = not in_block
                    nextline = True
                    break
            if nextline:
                continue

            if in_block:
                new_lines.append(self._handle_code(line))
            elif line.startswith('    '):
                # indentation syntax code block - leave as is
                new_lines.append(line)
            else:
                _re = re.compile(r'`.*?`')
                inline_matches = _re.findall(line)
                if inline_matches:
                    # need to not handle inline blocks as a text
                    for i, m in enumerate(inline_matches):
                        line = line.replace(m, '<inline_block>%s</inline_block>' % i)
                    line = self._handle_non_code(line)
                    for i, m in enumerate(inline_matches):
                        line = line.replace('<inline_block>%s</inline_block>' % i, m)
                    new_lines.append(line)
                else:
                    new_lines.append(self._handle_non_code(line))
        return new_lines

    def _handle_code(self, text):
        """Return a string that will replace ``text`` in the final text
        output. ``text`` is code.

        """
        text = '    ' + text
        return text

    def _handle_non_code(self, text):
        """Return a string that will replace ``text`` in the final text
        output. ``text`` is *not* code.

        """
        _re = re.compile(r'(\b)(\S+)/(\S+)#(\d+)(\b)')
        text = _re.sub(self._convert_user_repo_ticket, text)

        _re = re.compile(r'(\b)(\S+)#(\d+)(\b)')
        text = _re.sub(self._convert_user_ticket, text)

        _re = re.compile(r'(\s|^)(#\d+)')
        text = _re.sub(self._convert_ticket, text)

        _re = re.compile(r'(\b)(\S+)/(\S+)@([0-9a-f]{40})(\b)')
        text = _re.sub(self._convert_user_repo_sha, text)

        _re = re.compile(r'(\b)(\S+)@([0-9a-f]{40})(\b)')
        text = _re.sub(self._convert_user_sha, text)

        _re = re.compile(r'(\s|^)([0-9a-f]{40})(\s|$)')
        text = _re.sub(self._convert_sha, text)

        _re = re.compile(r'~~(.*?)~~',)
        text = _re.sub(self._convert_strikethrough, text)

        return text

    def _gh_commit_url(self, project, sha, title):
        return u'[%s](%s)' % (title, self.gh_base_url + project + '/commit/' + sha)

    def _gh_ticket_url(self, project, tid, title):
        return u'[%s](%s)' % (title, self.gh_base_url + project + '/issues/' + str(tid))

    def _convert_sha(self, m):
        return '%s[%s]%s' % (m.group(1), m.group(2)[:6], m.group(3))

    def _convert_ticket(self, m):
        return '%s[%s]' % m.groups()

    def _convert_user_ticket(self, m):
        user = m.group(2)
        tid = m.group(3)
        if self.gh_project.startswith(user + '/'):
            return '%s[%s]%s' % (m.group(1), '#' + tid, m.group(4))
        return m.group(0)

    def _convert_user_repo_ticket(self, m):
        project = '%s/%s' % (m.group(2), m.group(3))
        tid = m.group(4)
        if project == self.gh_project:
            return '%s[%s]%s' % (m.group(1), '#' + tid, m.group(5))
        title = project + '#' + tid
        return ''.join([m.group(1),
                        self._gh_ticket_url(project, tid, title),
                        m.group(5)])

    def _convert_user_sha(self, m):
        user = m.group(2)
        sha = m.group(3)
        if self.gh_project.startswith(user + '/'):
            return '%s[%s]%s' % (m.group(1), sha[:6], m.group(4))
        return m.group(0)

    def _convert_user_repo_sha(self, m):
        project = '%s/%s' % (m.group(2), m.group(3))
        sha = m.group(4)
        if project == self.gh_project:
            return '%s[%s]%s' % (m.group(1), sha[:6], m.group(5))
        title = project + '@' + sha[:6]
        return ''.join([m.group(1),
                        self._gh_commit_url(project, sha, title),
                        m.group(5)])

    def _convert_strikethrough(self, m):
        return '<s>%s</s>' % m.group(1)

    def _codeblock_syntax(self, text):
        return '\n    :::%s' % text
