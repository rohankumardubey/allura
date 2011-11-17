import bson
import datetime
import json
import logging
import re
import sys

import colander as col

from ming.orm import ThreadLocalORMSession
from pylons import g

from allura import model as M
from allura.lib import helpers as h

log = logging.getLogger(__name__)

class TroveCategory():
    def __init__(self, root_type=''):
        self.root_type = root_type

    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        cat = M.TroveCategory.query.get(fullname=cstruct)
        if not cat:
            raise col.Invalid(node,
                    '"%s" is not a valid trove category.' % cstruct)
        if not cat.fullpath.startswith(self.root_type):
            raise col.Invalid(node,
                    '"%s" is not a valid "%s" trove category.' %
                    (cstruct, self.root_type))
        return cat

class User():
    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        user = M.User.by_username(cstruct)
        if not user:
            raise col.Invalid(node,
                    'Invalid username "%s".' % cstruct)
        return user

class ProjectName(object):
    def __init__(self, name, shortname):
        self.name = name
        self.shortname = shortname

class ProjectNameType():
    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        name = cstruct
        shortname = re.sub("[^A-Za-z0-9]", "", name).lower()
        length = len(shortname)
        if length < 3 or length > 15:
            raise col.Invalid(node,
                    'Project shortname "%s" must be between 3 and 15 '
                    'characters.' % shortname)
        return ProjectName(name, shortname)

class ProjectShortnameType():
    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        col.Length(min=3, max=15)(node, cstruct)
        col.Regex(r'^[A-z][-A-z0-9]{2,}$',
            msg='Project shortname must begin with a letter, can '
                'contain letters, numbers, and dashes, and must be '
                '3-15 characters in length.')(node, cstruct)
        return cstruct.lower()

class Award():
    def __init__(self, nbhd):
        self.nbhd = nbhd

    def deserialize(self, node, cstruct):
        if cstruct is col.null:
            return col.null
        award = M.Award.query.find(dict(short=cstruct,
            created_by_neighborhood_id=self.nbhd._id)).first()
        if not award:
            # try to look up the award by _id
            award = M.Award.query.find(dict(_id=bson.ObjectId(cstruct),
                created_by_neighborhood_id=self.nbhd._id)).first()
        if not award:
            raise col.Invalid(node,
                    'Invalid award "%s".' % cstruct)
        return award

class TroveAudiences(col.SequenceSchema):
    trove_audience = col.SchemaNode(TroveCategory("Intended Audience"))

class TroveLicenses(col.SequenceSchema):
    trove_license = col.SchemaNode(TroveCategory("License"))

class Labels(col.SequenceSchema):
    label = col.SchemaNode(col.Str())

class Project(col.MappingSchema):
    name = col.SchemaNode(ProjectNameType())
    shortname = col.SchemaNode(ProjectShortnameType(), missing=None)
    summary = col.SchemaNode(col.Str(), missing='')
    description = col.SchemaNode(col.Str(), missing='')
    admin = col.SchemaNode(User())
    private = col.SchemaNode(col.Bool(), missing=False)
    labels = Labels(missing=[])
    external_homepage = col.SchemaNode(col.Str(), missing='')
    trove_audiences = TroveAudiences(validator=col.Length(max=6), missing=[])
    trove_licenses = TroveLicenses(validator=col.Length(max=6), missing=[])

class Projects(col.SequenceSchema):
    project = Project()

class Object(object):
    def __init__(self, d):
        self.__dict__.update(d)

def create_project(p, nbhd, options):
    M.session.artifact_orm_session._get().skip_mod_date = True
    shortname = p.shortname or p.name.shortname
    project = M.Project.query.get(shortname=shortname,
            neighborhood_id=nbhd._id)

    if project and not (options.update and p.shortname):
        log.warning('Skipping existing project "%s". To update an existing '
                    'project you must provide the project shortname and run '
                    'this script with --update.' % shortname)
        return 0

    if not project:
        log.info('Creating project "%s".' % shortname)
        project = nbhd.register_project(shortname,
                                        p.admin,
                                        project_name=p.name.name,
                                        private_project=p.private)
    else:
        log.info('Updating project "%s".' % shortname)

    project.notifications_disabled = True
    project.summary = p.summary
    project.short_description = p.description
    project.labels = p.labels
    project.external_homepage = p.external_homepage
    project.last_updated = datetime.datetime.utcnow()
    project.trove_audience = set(a._id for a in p.trove_audiences)
    project.trove_license = set(l._id for l in p.trove_licenses)
    for a in p.awards:
        M.AwardGrant(app_config_id=bson.ObjectId(),
                tool_version=dict(neighborhood='0'), award_id=a._id,
                granted_to_project_id=project._id,
                granted_by_neighborhood_id=nbhd._id)
    project.notifications_disabled = False
    with h.push_context(project._id):
        ThreadLocalORMSession.flush_all()
        g.post_event('project_updated')
    return 0

def main(options):
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(getattr(logging, options.log_level.upper()))
    log.debug(options)

    nbhd = M.Neighborhood.query.get(name=options.neighborhood)
    if not nbhd:
        return 'Invalid neighborhood "%s".' % options.neighborhood

    data = json.load(open(options.file, 'r'))
    project = Project()
    project.add(col.SchemaNode(col.Sequence(),
                               col.SchemaNode(Award(nbhd)),
                               name='awards', missing=[]))
    schema = col.SchemaNode(col.Sequence(), project, name='project')
    projects = schema.deserialize(data)
    log.debug(projects)

    for p in projects:
        r = create_project(Object(p), nbhd, options)
        if r != 0:
            return r
    return 0

def parse_options():
    import argparse
    parser = argparse.ArgumentParser(
            description='Import Allura project(s) from JSON file')
    parser.add_argument('file', metavar='JSON_FILE', type=str,
            help='Path to JSON file containing project data.')
    parser.add_argument('neighborhood', metavar='NEIGHBORHOOD', type=str,
            help='Destination Neighborhood shortname.')
    parser.add_argument('--log', dest='log_level', default='INFO',
            help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).')
    parser.add_argument('--update', dest='update', default=False,
            action='store_true',
            help='Update existing projects. Without this option, existing '
                 'projects will be skipped.')
    return parser.parse_args()

if __name__ == '__main__':
    sys.exit(main(parse_options()))
