# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006-2008 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
# Copyright (C) 2007-2008 Henry Obein <henry@itaapy.com>
# Copyright (C) 2008 Matthieu France <matthieu@itaapy.com>
# Copyright (C) 2008 Nicolas Deram <nicolas@itaapy.com>
# Copyright (C) 2010 Alexis Huet <alexis@itaapy.com>
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

# Import from itools
from itools.core import merge_dicts
from itools.datatypes import String, Unicode, Boolean
from itools.gettext import MSG
from itools.handlers import checkid
from itools.fs import FileName
from itools.uri import Path
from itools.web import STLForm, ERROR
from itools.xapian import AndQuery, OrQuery, PhraseQuery

# Import from ikaaro
from buttons import AddButton
from datatypes import FileDataType
from folder_views import Folder_BrowseContent
import messages
from registry import get_resource_class
from utils import get_base_path_query, reduce_string


###########################################################################
# Browse class
###########################################################################



class AddBase_BrowseContent(Folder_BrowseContent):
    access = 'is_allowed_to_edit'
    context_menus = []

    table_template = '/ui/html/addbase_browse_table.xml'
    search_template = '/ui/html/addbase_browse_search.xml'
    query_schema = merge_dicts(Folder_BrowseContent.query_schema,
                               Folder_BrowseContent.search_schema)

    folder_classes = ()
    item_classes = ()

    # Table
    table_columns = [
        ('checkbox', None),
        ('icon', None),
        ('name', MSG(u'Name')),
        ('mtime', MSG(u'Last Modified')),
        ('last_author', MSG(u'Last Author')),
        ('size', MSG(u'Size')),
        ('workflow_state', MSG(u'State'))]


    def get_folder_classes(self):
        if self.folder_classes:
            return self.folder_classes
        from folder import Folder
        return (Folder,)


    @classmethod
    def get_item_classes(self):
        if self.item_classes:
            return self.item_classes
        from resource_ import DBResource
        return (DBResource,)


    def is_folder(self, resource):
        bases = self.get_folder_classes()
        return isinstance(resource, bases)


    def get_item_value(self, resource, context, item, column):
        brain, item_resource = item
        if column == 'checkbox':
            # radiobox
            id = str(resource.get_canonical_path().get_pathto(brain.abspath))
            id += self.resource_action
            return id, False
        elif column == 'name':
            id = str(resource.get_canonical_path().get_pathto(brain.abspath))
            if self.is_folder(item_resource):
                site_root = resource.get_site_root()
                path_to_item = site_root.get_pathto(item_resource)
                url_dic = {'target': str(path_to_item),
                           # Avoid search conservation
                           'search_term': None,
                           'search_field': None,
                           'search_subfolders': None}
                url = context.uri.replace(**url_dic)
            else:
                url = None
            title = item_resource.get_title()
            return title, url
        else:
            return Folder_BrowseContent.get_item_value(self, resource, context,
                       item, column)


    def get_items(self, resource, context, *args):
        target = context.get_form_value('target')
        if target:
            site_root_abspath = resource.get_site_root().get_abspath()
            if target.startswith('/'):
                target = target.lstrip('/')
            target = site_root_abspath.resolve2(target)
            resource = resource.get_resource(target)
        else:
            if not self.is_folder(resource):
                resource = resource.parent
        items = Folder_BrowseContent.get_items(self, resource, context, *args)
        return items


    def get_search_namespace(self, resource, context):
        namespace = Folder_BrowseContent.get_search_namespace(self, resource,
                        context)
        target = context.get_form_value('target')
        if target:
            namespace['target'] = target
        else:
            namespace['target'] = resource.get_abspath()
        namespace['mode'] = context.get_form_value('mode')
        return namespace


    table_actions = [AddButton]


    def get_actions_namespace(self, resource, context, items):
        button = AddButton
        actions = []
        js = "javascript:select_element('%s', $(this).attr('value'),'')"
        js = js % self.element_to_add
        actions.append(
            {'value': '',
             'title': button.title,
             'id': button.css,
             'onclick': js})
        return actions



class AddImage_BrowseContent(AddBase_BrowseContent):

    @classmethod
    def get_item_classes(cls):
        if cls.item_classes:
            return cls.item_classes
        from file import Image
        from folder import Folder
        return (Image, Folder)


    def get_items(self, resource, context, *args):
        query = []
        # search query
        c_query = context.query
        search_term = c_query['search_term'].strip()
        field = c_query['search_field']
        search_subfolders = c_query['search_subfolders']

        # FIXME
        # Should use get_item_classes

        target = context.get_form_value('target')
        if target:
            site_root_abspath = resource.get_site_root().get_abspath()
            if target.startswith('/'):
                target = target.lstrip('/')
            target = site_root_abspath.resolve2(target)
            container = resource.get_resource(target)
        else:
            container = resource

        if not self.is_folder(container):
            container = container.parent

        if search_subfolders is True:
            abspath = str(container.get_canonical_path())
            query.append(get_base_path_query(abspath))
        else:
            parent_path = str(container.get_abspath())
            query.append(PhraseQuery('parent_path', parent_path))
        if search_term:
            query.append(PhraseQuery(field, search_term))

        # Images
        image_query = PhraseQuery('is_image', True)

        # Folders
        folder_query = PhraseQuery('is_folder', True)
        query.append(OrQuery(image_query, folder_query))

        query = AndQuery(*query)
        return context.root.search(query)



    def get_item_value(self, resource, context, item, column):
        brain, item_resource = item
        if column == 'checkbox':
            if self.is_folder(item_resource):
                return None
            # radiobox
            id = str(resource.get_canonical_path().get_pathto(brain.abspath))
            id += self.resource_action
            return id, False
        elif column == 'name':
            id = str(resource.get_canonical_path().get_pathto(brain.abspath))
            if self.is_folder(item_resource):
                site_root = resource.get_site_root()
                path_to_item = site_root.get_pathto(item_resource)
                url_dic = {'target': str(path_to_item),
                           # Avoid search conservation
                           'search_term': None,
                           'search_field': None,
                           'search_subfolders': None}
                url = context.uri.replace(**url_dic)
            else:
                url = None
            title = item_resource.get_title()
            return title, url
        elif column == 'icon':
            if self.is_folder(item_resource):
                # icon
                path_to_icon = item_resource.get_resource_icon(48)
                if path_to_icon.startswith(';'):
                    path_to_icon = Path('%s/' % brain.name).resolve(path_to_icon)
            else:
                path = resource.get_pathto(item_resource)
                path_to_icon = ";thumb?width48=&height=48"
                if path:
                    path_to_resource = Path(str(path) + '/')
                    path_to_icon = path_to_resource.resolve(path_to_icon)
            return path_to_icon
        else:
            return Folder_BrowseContent.get_item_value(self, resource, context,
                    item, column)



class AddMedia_BrowseContent(AddBase_BrowseContent):

    @classmethod
    def get_item_classes(cls):
        if cls.item_classes:
            return cls.item_classes
        from file import Flash, Video
        return (Flash, Video)


###########################################################################
# Interface to add images from the TinyMCE editor
###########################################################################



class DBResource_AddBase(STLForm):
    """Base class for 'DBResource_AddImage' and 'DBResource_AddLink' (used
    by the Web Page editor).
    """

    access = 'is_allowed_to_edit'
    template = '/ui/html/popup.xml'

    element_to_add = None

    schema = {
        'target_path': String(mandatory=True),
        'target_id': String(default=None),
        'mode': String(default='')}

    search_schema = {
        'search_field': String,
        'search_term': Unicode,
        'search_subfolders': Boolean(default=False),
    }

    # This value must be set in subclass
    browse_content_class = None
    query_schema = merge_dicts(Folder_BrowseContent.query_schema,
                               search_schema, target=String)
    action_upload_schema = merge_dicts(schema,
                                       file=FileDataType(mandatory=True))


    def get_configuration(self):
        return {}


    def get_root(self, context):
        return context.resource.get_site_root()


    def get_start(self, resource):
        from file import File
        if isinstance(resource, File):
            return resource.parent
        return resource


    def can_upload(self, cls):
        bases = self.get_item_classes()
        return issubclass(cls, bases)


    def get_item_classes(self):
        return self.browse_content_class.get_item_classes()



    def get_namespace(self, resource, context):
        from folder import Folder

        # For the breadcrumb
        start = self.get_start(resource)

        # Get the query parameters
        target_path = context.get_form_value('target')
        # Get the target folder
        site_root = resource.get_site_root()
        site_root_abspath = site_root.get_abspath()
        if target_path is None:
            if isinstance(start, Folder):
                target = start
            else:
                target = start.parent
        else:
            target = site_root.get_resource(target_path)
            if target_path.startswith('/'):
                target_path = target_path.lstrip('/')
            target_path = site_root_abspath.resolve2(target_path)
            target = resource.get_resource(target_path)

        # The breadcrumb
        breadcrumb = []
        node = target
        while node:
            path_to_node = site_root_abspath.get_pathto(node.get_abspath())
            url_dic = {'target': str(path_to_node),
                       # Avoid search conservation
                       'search_term': None,
                       'search_field': None,
                       'search_subfolders': None}
            url = context.uri.replace(**url_dic)
            title = node.get_title()
            short_title = reduce_string(title, 12, 40)
            quoted_title = short_title.replace("'", "\\'")
            breadcrumb.insert(0, {'name': node.name,
                                  'title': title,
                                  'short_title': short_title,
                                  'quoted_title': quoted_title,
                                  'url': url})
            node = node.parent

        # Avoid general template
        context.content_type = 'text/html; charset=UTF-8'

        # Build and return the namespace
        namespace = self.get_configuration()
        additional_javascript = self.get_additional_javascript(context)
        namespace['text'] = self.text_values
        namespace['additional_javascript'] = additional_javascript
        namespace['target_path'] = str(target.get_abspath())
        namespace['breadcrumb'] = breadcrumb
        namespace['element_to_add'] = self.element_to_add
        namespace['target_id'] = context.get_form_value('target_id')
        namespace['message'] = context.message
        namespace['mode'] = context.get_form_value('mode')
        namespace['scripts'] = self.get_scripts(context)
        namespace['styles'] = site_root.get_skin(context).get_styles(context)
        browse_content = self.browse_content_class(\
                           element_to_add=self.element_to_add,
                           resource_action=self.get_resource_action(context))
        namespace['browse_table'] = browse_content.GET(resource, context)
        return namespace


    def get_scripts(self, context):
        mode = context.get_form_value('mode')
        if mode == 'tiny_mce':
            return ['/ui/tiny_mce/javascript.js',
                    '/ui/tiny_mce/tiny_mce_src.js',
                    '/ui/tiny_mce/tiny_mce_popup.js']
        return []


    def get_additional_javascript(self, context):
        mode = context.get_form_value('mode')
        if mode != 'input':
            return ''

        additional_javascript = """
            function select_element(type, value, caption) {
                window.opener.$("#%s").val(value);
                window.close();
            }
            """

        target_id = context.get_form_value('target_id')
        return additional_javascript % target_id


    def action_upload(self, resource, context, form):
        filename, mimetype, body = form['file']
        name, type, language = FileName.decode(filename)

        # Check the filename is good
        name = checkid(name)
        if name is None:
            context.message = messages.MSG_BAD_NAME
            return

        # Get the container
        container = context.root.get_resource(form['target_path'])

        # Check the name is free
        if container.get_resource(name, soft=True) is not None:
            context.message = messages.MSG_NAME_CLASH
            return

        # Check it is of the expected type
        cls = get_resource_class(mimetype)
        if not self.can_upload(cls):
            error = u'The given file is not of the expected type.'
            context.message = ERROR(error)
            return

        # Add the image to the resource
        child = container.make_resource(name, cls, body=body, format=mimetype,
                                        filename=filename, extension=type)
        # Get the path
        path = resource.get_pathto(child)
        action = self.get_resource_action(context)
        if action:
            path = '%s%s' % (path, action)
        # Return javascript
        scripts = self.get_scripts(context)
        context.add_script(*scripts)
        return self.get_javascript_return(context, path)


    def get_javascript_return(self, context, path):
        return """
            <script type="text/javascript">
              %s
              select_element('%s', '%s', '');
            </script>""" % (self.get_additional_javascript(context),
                            self.element_to_add, path)


    def get_resource_action(self, context):
        return ''



class DBResource_AddLink(DBResource_AddBase):

    element_to_add = 'link'
    browse_content_class = AddBase_BrowseContent

    action_add_resource_schema = merge_dicts(DBResource_AddBase.schema,
                                             title=String(mandatory=True))

    text_values = {'title': MSG(u'Insert link'),
       'browse': MSG(u'Browse and link to a File from the workspace'),
       'extern': MSG(u'Type the URL of an external resource'),
       'insert': MSG(u'Create a new page and link to it:'),
       'upload': MSG(u'Upload a file to the current folder and link to it:'),
       'method': ';add_link'}


    def get_configuration(self):
        return {
            'show_browse': True,
            'show_external': True,
            'show_insert': True,
            'show_upload': True}


    def action_add_resource(self, resource, context, form):
        mode = form['mode']
        name = checkid(form['title'])
        # Check name validity
        if name is None:
            context.message = MSG(u"Invalid title.")
            return
        # Get the container
        root = context.root
        container = root.get_resource(context.get_form_value('target_path'))
        # Check the name is free
        if container.get_resource(name, soft=True) is not None:
            context.message = messages.MSG_NAME_CLASH
            return
        # Get the type of resource to add
        cls = self.get_page_type(mode)
        # Create the resource
        child = container.make_resource(name, cls)
        path = context.resource.get_pathto(child)
        scripts = self.get_scripts(context)
        context.add_script(*scripts)
        return self.get_javascript_return(context, path)


    def get_page_type(self, mode):
        """Return the type of page to add corresponding to the mode
        """
        if mode == 'tiny_mce':
            from webpage import WebPage
            return WebPage
        raise ValueError, 'Incorrect mode %s' % mode



class DBResource_AddImage(DBResource_AddBase):

    element_to_add = 'image'
    browse_content_class = AddImage_BrowseContent

    text_values = {'title': MSG(u'Insert image'),
       'browse': MSG(u'Browse and insert an Image from the workspace'),
       'extern': None,
       'insert': None,
       'upload': MSG(u'Upload an image to the current folder and insert it:'),
       'method': ';add_image'}


    def get_configuration(self):
        return {
            'show_browse': True,
            'show_external': False,
            'show_insert': False,
            'show_upload': True}


    def get_resource_action(self, context):
        mode = context.get_form_value('mode')
        if mode == 'tiny_mce':
            return '/;download'
        return DBResource_AddBase.get_resource_action(self, context)



class DBResource_AddMedia(DBResource_AddImage):

    element_to_add = 'media'
    browse_content_class = AddMedia_BrowseContent

    text_values = {'title': MSG(u'Insert media'),
       'browse': MSG(u'Browse and insert a Media from the workspace'),
       'extern': MSG(u'Type the URL of an external media'),
       'insert': None,
       'upload': MSG(u'Upload a media to the current folder and insert it:'),
       'method': ';add_media'}


    def get_configuration(self):
        return {
            'show_browse': True,
            'show_external': True,
            'show_insert': False,
            'show_upload': True}




