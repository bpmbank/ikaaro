# -*- coding: UTF-8 -*-
# Copyright (C) 2006 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2006-2007 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from the Standard Library
from os import fdopen
import sys
from tempfile import mkstemp

# Import from itools
from itools.catalog import Catalog
from itools.datatypes import Boolean
from itools.handlers import ConfigFile, SafeDatabase
from itools.uri import get_absolute_reference2
from itools import vfs
from itools.web import Server as BaseServer

# Import from ikaaro
from handlers import Metadata
from folder import Folder
from registry import get_object_class
from utils import is_pid_running
from versioning import VersioningAware
from website import WebSite



def ask_confirmation(message):
    sys.stdout.write(message)
    sys.stdout.flush()
    line = sys.stdin.readline()
    line = line.strip().lower()
    return line == 'y'



def get_config(target):
    return ConfigFile('%s/config.conf' % target)



class Server(BaseServer):

    def __init__(self, target, address=None, port=None, debug=False):
        target = get_absolute_reference2(target)
        self.target = target

        # Load the config
        config = get_config(target)

        # Load Python packages and modules
        modules = config.get_value('modules')
        if modules is not None:
            for name in modules.split():
                name = name.strip()
                exec('import %s' % name)

        # Find out the IP to listen to
        if address:
            pass
        else:
            address = config.get_value('address')

        # Find out the port to listen
        if port:
            pass
        else:
            port = config.get_value('port')
            if port is not None:
                port = int(port)

        # The database
        database = SafeDatabase('%s/database.commit' % target.path)
        self.database = database
        # The catalog
        self.catalog = Catalog('%s/catalog' % target)

        # Find out the root class
        path = target.resolve2('database/.metadata')
        metadata = database.get_handler(path, cls=Metadata)
        format = metadata.get_property('format')
        cls = get_object_class(format)
        # Build the root object
        root = cls(metadata)
        root.name = root.class_title

        # Logs
        path = target.path
        access_log = '%s/log/access' % path
        error_log = '%s/log/error' % path
        if debug or config.get_value('debug', type=Boolean, default=False):
            debug_log = '%s/log/debug' % path
        else:
            debug_log = None

        # Events
        self.objects_added = set()
        self.objects_changed = set()
        self.objects_removed = set()

        # Initialize
        BaseServer.__init__(self, root, address=address, port=port,
                            access_log=access_log, error_log=error_log,
                            debug_log=debug_log, pid_file='%s/pid' % path)


    #######################################################################
    # API / Private
    #######################################################################
    def get_pid(self):
        try:
            pid = open('%s/pid' % self.target.path).read()
        except IOError:
            return None

        pid = int(pid)
        if is_pid_running(pid):
            return pid
        return None


    def send_email(self, message):
        spool = self.target.resolve2('spool')
        spool = str(spool.path)
        tmp_file, tmp_path = mkstemp(dir=spool)
        file = fdopen(tmp_file, 'w')
        try:
            file.write(message.as_string())
        finally:
            file.close()


    def get_databases(self):
        return [self.database, self.catalog]


    def abort_transaction(self, context):
        # Clear events
        self.objects_removed.clear()
        self.objects_added.clear()
        self.objects_changed.clear()
        # Follow-up
        BaseServer.abort_transaction(self, context)


    def before_commit(self):
        catalog = self.catalog
        # Removed
        for object in self.objects_removed:
            path = str(object.get_abspath())
            catalog.unindex_document(path)
        self.objects_removed.clear()

        # Added
        for object in self.objects_added:
            if isinstance(object, Folder):
                for x in object.traverse_objects():
                    catalog.index_document(x)
                    if isinstance(x, VersioningAware):
                        x.commit_revision()
            else:
                catalog.index_document(object)
                if isinstance(object, VersioningAware):
                    object.commit_revision()
        self.objects_added.clear()

        # Changed
        for object in self.objects_changed:
            path = str(object.get_abspath())
            catalog.unindex_document(path)
            catalog.index_document(object)
            if isinstance(object, VersioningAware):
                object.commit_revision()
        self.objects_changed.clear()


    #######################################################################
    # API / Public
    #######################################################################
    def get_site_root(self, hostname):
        root = self.root

        sites = [root]
        for site in root.search_objects(object_class=WebSite):
            sites.append(site)

        for site in sites:
            if hostname in site.get_property('ikaaro:vhosts'):
                return site

        return root


    def remove_object(self, object):
        self.objects_removed.add(object)


    def add_object(self, object):
        self.objects_added.add(object)


    def change_object(self, object):
        self.objects_changed.add(object)


