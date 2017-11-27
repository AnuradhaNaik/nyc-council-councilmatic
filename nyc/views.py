from django.shortcuts import render
from django.http import HttpResponsePermanentRedirect, HttpResponseNotFound, HttpResponse, HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.db import transaction, connection, connections

from datetime import date, timedelta
import re
from collections import namedtuple

from .utils import create_google_cal_link, create_ics_output

from nyc.models import NYCBill

from councilmatic_core.models import Event, Organization, Bill
from councilmatic_core.views import *
from haystack.query import SearchQuerySet


class NYCIndexView(IndexView):
    template_name = 'nyc/index.html'
    bill_model = NYCBill

class NYCAboutView(AboutView):
    template_name = 'nyc/about.html'

class NYCBillDetailView(BillDetailView):
    model = NYCBill

    def dispatch(self, request, *args, **kwargs):
        slug = self.kwargs['slug']

        try:
            bill = self.model.objects.get(slug=slug)
            response = super().dispatch(request, *args, **kwargs)
        except NYCBill.DoesNotExist:
            bill = None

        if bill is None:
            try:
                bill = self.model.objects.get(slug__startswith=slug)
                response = HttpResponsePermanentRedirect(reverse('bill_detail', args=[bill.slug]))
            except NYCBill.DoesNotExist:
                try: 
                    one, two, three, four = slug.split('-')
                    short_slug = slug.replace('-' + four, '')
                    bill = self.model.objects.get(slug__startswith=short_slug)
                    response = HttpResponsePermanentRedirect(reverse('bill_detail', args=[bill.slug]))
                except:
                    response = HttpResponseNotFound()

        return response

class NYCCommitteeDetailView(CommitteeDetailView):
    model = Organization

    def dispatch(self, request, *args, **kwargs):
        slug = self.kwargs['slug']

        try:
            committee = self.model.objects.get(slug=slug)
            response = super().dispatch(request, *args, **kwargs)
        except Organization.DoesNotExist:
            committee = None

        if committee is None:
            try:
                slug = slug.replace(',', '').replace('\'', '')
                committee = self.model.objects.get(slug__startswith=slug)
                response = HttpResponsePermanentRedirect(reverse('committee_detail', args=[committee.slug]))
            except Organization.DoesNotExist:
                response = HttpResponseNotFound()

        return response

class NYCPersonDetailView(PersonDetailView):
    model = Person

    def dispatch(self, request, *args, **kwargs):
        slug = self.kwargs['slug']

        try:
            person = self.model.objects.get(slug=slug)
            response = super().dispatch(request, *args, **kwargs)
        except Person.DoesNotExist:
            person = None

        if person is None:
            person_name = slug.replace('-', ' ')
            try:
                slug = slug.replace(',', '').replace('\'', '').replace('--', '-')
                person = self.model.objects.get(slug__startswith=slug)
                response = HttpResponsePermanentRedirect(reverse('person', args=[person.slug]))

            except Person.MultipleObjectsReturned:
                person_name = slug.replace('-', ' ').replace('.', '')
                # If duplicate person has middle initial.
                if re.match(r'\w+[\s.-]\w+[\s.-]\w+', slug) is not None:
                    person_name = re.sub(r'(\w+\s\w+)(\s\w+)', r'\1.\2', person_name)
                person = self.model.objects.get(name__iexact=person_name)
                response = HttpResponsePermanentRedirect(reverse('person', args=[person.slug]))
            except Person.DoesNotExist:
                response = HttpResponseNotFound()

        return response

class NYCBillWidgetView(BillWidgetView):
    model = NYCBill

class NYCCommitteesView(CommitteesView):

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        context = super(CommitteesView, self).get_context_data(**kwargs)

        committees = Organization.committees().filter(name__startswith='Committee')

        context['committees'] = [c for c in committees if c.memberships.all()]

        subcommittees = Organization.committees().filter(name__startswith='Subcommittee')
        context['subcommittees'] = [c for c in subcommittees if c.memberships.all()]

        taskforces = Organization.committees().filter(name__startswith='Task Force')
        context['taskforces'] = [c for c in taskforces if c.memberships.all()]

        return context

class NYCEventDetailView(EventDetailView):
    template_name = 'nyc/event.html'
    model = Event

    def get_context_data(self, **kwargs):
        context = super(EventDetailView, self).get_context_data(**kwargs)
        event = context['event']

        event_url = create_google_cal_link(event)
        context['event_url'] = event_url

        # Logic for getting relevant board report information.
        with connection.cursor() as cursor:
            query = '''
                SELECT distinct
                    b.identifier,
                    b.slug,
                    b.description,
                    i.order
                FROM councilmatic_core_bill AS b
                INNER JOIN councilmatic_core_eventagendaitem as i
                ON i.bill_id=b.ocd_id
                WHERE i.event_id='{}'
                GROUP BY
                    b.identifier,
                    b.slug,
                    b.description,
                    i.order 
                ORDER BY i.order
                '''.format(event.ocd_id)

            cursor.execute(query)

            # Get field names
            columns = [c[0] for c in cursor.description]
        
            # Create a named tuple
            bill_tuple = namedtuple('BillProperties', columns, rename=True)
            # Put results inside a list with assigned fields (from namedtuple)
            related_bills = [bill_tuple(*r) for r in cursor]

            context['related_bills'] = related_bills

        return context

# Views for calendar exports.
def ical_export(request, slug):
    event = Event.objects.get(slug=slug)
    output = create_ics_output(event)
  
    response = HttpResponse(output, content_type='text/calendar')
    response['Content-Disposition'] = 'attachment; filename={}.ics'.format(event.slug) 

    return response


class NYCCouncilmaticFacetedSearchView(CouncilmaticFacetedSearchView):

    def build_form(self, form_kwargs=None):
        form = super(CouncilmaticFacetedSearchView, self).build_form(form_kwargs=form_kwargs)

        # For faceted search functionality.
        if form_kwargs is None:
            form_kwargs = {}

        form_kwargs['selected_facets'] = self.request.GET.getlist("selected_facets")

        # For remaining search functionality.
        data = None
        kwargs = {
            'load_all': self.load_all,
        }

        sqs = SearchQuerySet().facet('bill_type')\
                      .facet('sponsorships', sort='index')\
                      .facet('controlling_body')\
                      .facet('inferred_status')\
                      .highlight()

        if form_kwargs:
            kwargs.update(form_kwargs)

        if len(self.request.GET):
            data = self.request.GET
            dataDict = dict(data)

        if self.searchqueryset is not None:
            kwargs['searchqueryset'] = sqs

            try:
                for el in dataDict['sort_by']:
                    # Do this, because sometimes the 'el' may include a '?' from the URL
                    if 'date' in el:
                        try:
                            dataDict['ascending']
                            kwargs['searchqueryset'] = sqs.order_by('last_action_date')
                        except:
                            kwargs['searchqueryset'] = sqs.order_by('-last_action_date')
                    if 'title' in el:
                        try:
                            dataDict['descending']
                            kwargs['searchqueryset'] = sqs.order_by('-sort_name')
                        except:
                            kwargs['searchqueryset'] = sqs.order_by('sort_name')
                    if 'relevance' in el:
                        kwargs['searchqueryset'] = sqs

            except:
                kwargs['searchqueryset'] = sqs.order_by('-last_action_date')

        return self.form_class(data, **kwargs)
