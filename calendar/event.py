# -*- coding: UTF-8 -*-
# Copyright (C) 2009 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2009 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2008 Nicolas Deram <nicolas@itaapy.com>
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
from datetime import date, datetime, time, timedelta

# Import from itools
from itools.core import freeze, merge_dicts
from itools.csv import Property
from itools.datatypes import Date, DateTime, Enumerate, String, Time, Unicode
from itools.gettext import MSG
from itools.web import ERROR, FormError, STLForm, get_context

# Import from ikaaro
from ikaaro.autoform import DatetimeWidget, ReadOnlyWidget
from ikaaro.autoform import location_widget, title_widget
from ikaaro.file import File
from ikaaro import messages
from ikaaro.registry import get_resource_class
from ikaaro.views_new import NewInstance
from calendar_views import CalendarView, resolution



class Status(Enumerate):

    default = 'TENTATIVE'

    options = [{'name': 'TENTATIVE', 'value': MSG(u'Tentative')},
               {'name': 'CONFIRMED', 'value': MSG(u'Confirmed')},
               {'name': 'CANCELLED', 'value': MSG(u'Cancelled')}]



class Event_Edit(CalendarView, STLForm):

    access = 'is_allowed_to_edit'
    title = MSG(u'Edit Event')
    template = '/ui/calendar/edit_event.xml'
    schema = {
        'title': Unicode(mandatory=True),
        'location': Unicode,
        'dtstart': Date(mandatory=True),
        'dtstart_time': Time,
        'dtend': Date(mandatory=True),
        'dtend_time': Time,
        'description': Unicode,
        'status': Status(mandatory=True)}


    def _get_form(self, resource, context):
        """ Check start is before end.
        """
        form = STLForm._get_form(self, resource, context)
        start_date = form['dtstart']
        start_time = form.get('dtstart_time', None) or time(0,0)
        end_date = form['dtend']
        end_time = form.get('dtend_time', None) or time(23,59)
        start = datetime.combine(start_date, start_time)
        end = datetime.combine(end_date, end_time)

        if start > end:
            msg = ERROR(u'Invalid dates.')
            raise FormError(msg)
        return form


    def get_namespace(self, resource, context):
        # Date start
        start = resource.metadata.get_property('dtstart')
        param = start.get_parameter('VALUE', '')
        start_date = Date.encode(start.value)
        start_time = Time.encode(start.value)[:5] if param != 'DATE' else None
        # Date end
        end = resource.metadata.get_property('dtend')
        param = end.get_parameter('VALUE', '')
        end_date = Date.encode(end.value)
        end_time = Time.encode(end.value)[:5] if param != 'DATE' else None

        # status is an enumerate
        status = resource.get_property('status')
        status = Status().get_namespace(status)

        # Show action buttons only if current user is authorized
        allowed = resource.parent.is_organizer_or_admin(context, resource)

        # The namespace
        namespace = {
            'action': ';edit',
            'dtstart': start_date,
            'dtstart_time': start_time,
            'dtend': end_date,
            'dtend_time': end_time,
            'remove': True,
            'firstday': self.get_first_day(),
            'status': status,
            'allowed': allowed}

        # Get values
        for key in self.schema:
            if key not in namespace:
                namespace[key] = resource.get_property(key)

        return namespace


    def action_edit_event(self, resource, context, form):
        # Test if current user is admin or organizer of this event
        if not resource.parent.is_organizer_or_admin(context, resource):
            message = ERROR(u'You are not authorized to modify this event.')
            context.message = message
            return

        # Update
        resource.update(context, form)
        # Ok
        context.message = messages.MSG_CHANGES_SAVED


    def action_remove_event(self, resource, context, form):
        # Remove
        calendar = resource.parent
        calendar.del_resource(resource.name)

        # Ok
        method = context.get_cookie('method') or 'monthly_view'
        goto = '../;%s?%s' % (method, date.today())

        message = ERROR(u'Event definitely deleted.')
        return context.come_back(message, goto=goto)


    def action_cancel(self, resource, context, form):
        goto = ';%s' % context.get_cookie('method') or 'monthly_view'
        return context.come_back(None, goto)



class Event_NewInstance(NewInstance):

    query_schema = merge_dicts(NewInstance.query_schema,
                               start=Date, start_time=Time,
                               end=Date, end_time=Time)

    schema = merge_dicts(NewInstance.schema,
                         start=Date(mandatory=True),
                         start_time=Time,
                         end=Date,
                         end_time=Time)
    widgets = freeze([
        ReadOnlyWidget('cls_description'),
        title_widget,
        DatetimeWidget('start', title=MSG(u'Start'),
                       tip=MSG(u'To add an event lasting all day long,'
                               u' leave time fields empty.')),
        DatetimeWidget('end', title=MSG(u'End')),
        location_widget(include_name=False)])


    def get_new_resource_name(self, form):
        return form['container'].get_new_id()


    def get_value(self, resource, context, name, datatype):
        if name in ('start', 'end'):
            return context.query[name] or date.today()

        proxy = super(Event_NewInstance, self)
        return proxy.get_value(resource, context, name, datatype)


    def _get_form(self, resource, context):
        form = super(Event_NewInstance, self)._get_form(resource, context)

        # Start
        start_time = form['start_time'] or time(0, 0)
        start = datetime.combine(form['start'], start_time)
        form['start'] = context.add_user_tzinfo(start)
        # End
        end_time = form['end_time'] or time(0, 0)
        end = datetime.combine(form['end'], end_time)
        form['end'] = context.add_user_tzinfo(end)

        return form


    def action(self, resource, context, form):
        # Get the container
        container = form['container']
        # Make the resource
        class_id = context.query['type']
        cls = get_resource_class(class_id)
        child = container.make_resource(form['name'], cls)
        # Set properties
        language = container.get_edit_languages(context)[0]
        title = Property(form['title'], lang=language)
        child.metadata.set_property('title', title)
        # Set properties / start
        dt = form['start']
        dt = Property(dt) if dt.time else Property(dt, VALUE='DATE')
        child.set_property('dtstart', dt)
        # Set properties / end
        dt = form['end']
        dt = Property(dt) if dt.time else Property(dt, VALUE='DATE')
        child.set_property('dtend', dt)
        # Ok
        goto = str(resource.get_pathto(child))
        return context.come_back(messages.MSG_NEW_RESOURCE, goto=goto)



class EventDateTime(DateTime):

    # TODO This comes from the iCal age, use something better
    parameters_schema = {'VALUE': String(multiple=False)}



class Event(File):

    class_id = 'event'
    class_title = MSG(u'Event')
    class_description = MSG(u'Calendar event')
    class_icon16 = 'icons/16x16/event.png'
    class_icon48 = 'icons/48x48/event.png'
    class_views = ['edit', 'links', 'backlinks', 'edit_state']


    class_schema = merge_dicts(
        File.class_schema,
        # Metadata
        dtstart=EventDateTime(source='metadata', indexed=True, stored=True),
        dtend=EventDateTime(source='metadata', indexed=True, stored=True),
        status=Status(source='metadata'),
        location=Unicode(source='metadata'),
        uid=Unicode(source='metadata'))


    def init_resource(self, body=None, filename=None, extension=None, **kw):
        if 'uid' not in kw:
            path =  self.get_abspath()
            context = get_context()
            authority = context.uri.authority
            uid = str(path) + '@%s' % authority
            kw['uid'] = uid
        File.init_resource(self, body=body, filename=filename,
                    extension=extension, **kw)


    def get_ns_event(self, day, resource_name=None, conflicts_list=freeze([]),
                     timetable=None, grid=False, starts_on=True, ends_on=True,
                     out_on=True):
        """Specify the namespace given on views to represent an event.

        day: date selected XXX not used for now
        conflicts_list: list of conflicting uids for current resource, [] if
            not used
        timetable: timetable index or None
        grid: current calculated view uses gridlayout
        starts_on, ends_on and out_on are used to adjust display.

        By default, we get:

          start: HH:MM, end: HH:MM,
            TIME: (HH:MM-HH:MM) or TIME: (HH:MM...) or TIME: (...HH:MM)
          or
          start: None,  end: None, TIME: None

          summary: 'summary of the event'
          status: 'status' (class: cal_conflict, if id in conflicts_list)
          ORGANIZER: 'organizer of the event'
        """
        ns = {
            'title': self.get_title(),
            'description': self.get_property('description'),
            'ORGANIZER': self.get_owner()}

        ###############################################################
        # Set dtstart and dtend values using '...' for events which
        # appear into more than one cell
        dtstart = self.get_property('dtstart')
        dtend = self.get_property('dtend')
        start_value_type = 'DATE-TIME' # FIXME

        ns['start'] = Time.encode(dtstart.time())[:5]
        ns['end'] = Time.encode(dtend.time())[:5]
        ns['TIME'] = None
        if grid:
            # Neither a full day event nor a multiple days event
            if start_value_type != 'DATE' and dtstart.date() == dtend.date():
                ns['TIME'] = '%s - %s' % (ns['start'], ns['end'])
            else:
                ns['start'] = ns['end'] = None
        elif not out_on:
            if start_value_type != 'DATE':
                value = ''
                if starts_on:
                    value = ns['start']
                    if ends_on:
                        value = value + '-'
                    else:
                        value = value + '...'
                if ends_on:
                    value = value + ns['end']
                    if not starts_on:
                        value = '...' + value
                ns['TIME'] = '(' + value + ')'

        ###############################################################
        # Set class for conflicting events or just from status value
        id = self.get_abspath()
        if id in conflicts_list:
            ns['status'] = 'cal_conflict'
        else:
            ns['status'] = 'cal_busy'
            status = self.get_property('status')
            if status:
                ns['status'] = status

        if not resource_name:
            id = str(id)
        else:
            id = '%s/%s' % (resource_name, id)
        ns['id'] = id

        return ns


    def update(self, context, form):
        """Return the properties dict, ready to be used by the add or update
        actions.
        """
        # Start
        dtstart = form['dtstart']
        dtstart_time = form['dtstart_time']
        if dtstart_time is None:
            dtstart = datetime.combine(dtstart, time(0, 0))
            dtstart = context.add_user_tzinfo(dtstart)
            dtstart = Property(dtstart, VALUE='DATE')
        else:
            dtstart = datetime.combine(dtstart, dtstart_time)
            dtstart = context.add_user_tzinfo(dtstart)
            dtstart = Property(dtstart)
        self.set_property('dtstart', dtstart)

        # End
        dtend = form['dtend']
        dtend_time = form['dtend_time']
        if dtend_time is None:
            dtend = datetime.combine(dtend, time(0, 0))
            dtend = dtend + timedelta(days=1) - resolution
            dtend = context.add_user_tzinfo(dtend)
            dtend = Property(dtend, VALUE='DATE')
        else:
            dtend = datetime.combine(dtend, dtend_time)
            dtend = context.add_user_tzinfo(dtend)
            dtend = Property(dtend)
        self.set_property('dtend', dtend)

        # Other
        context = get_context()
        language = self.get_edit_languages(context)[0]
        for key in self.class_schema:
            if key == 'dtstart' or key == 'dtend':
                continue
            value = form.get(key)
            if value is None:
                continue
            datatype = self.class_schema[key]
            if getattr(datatype, 'multilingual', False):
                self.set_property(key, Property(value, lang=language))
            else:
                self.set_property(key, value)


    # Views
    new_instance = Event_NewInstance()
    edit = Event_Edit()
