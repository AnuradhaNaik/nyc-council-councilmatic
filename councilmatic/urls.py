from django.conf.urls import include, url
from django.contrib import admin
from django.conf import settings
from haystack.query import SearchQuerySet
from councilmatic_core.views import CouncilmaticSearchForm, CouncilmaticFacetedSearchView
from councilmatic_core.feeds import CouncilmaticFacetedSearchFeed
from nyc.views import *
from nyc.feeds import *
from django.views.decorators.cache import never_cache

import notifications

from notifications.views import *

import django_rq

from councilmatic.settings import *

sqs = SearchQuerySet().facet('bill_type')\
                      .facet('sponsorships', sort='index')\
                      .facet('controlling_body')\
                      .facet('inferred_status')\
                      .highlight()

patterns = ([
    url(r'^admin/', include(admin.site.urls)),
    url(r'^committees/$', NYCCommitteesView.as_view(), name='committees'),
    url(r'^search/rss/',
        NYCCouncilmaticFacetedSearchFeed(), name='councilmatic_search_feed'),
    url(r'^search/', CouncilmaticFacetedSearchView(searchqueryset=sqs,
                                                   form_class=CouncilmaticSearchForm),
                     name='search'),
    url(r'^$', NYCIndexView.as_view(), name='index'),
    url(r'^about/$', NYCAboutView.as_view(), name='about'),
    url(r'^legislation/(?P<slug>[^/]+)/$', NYCBillDetailView.as_view(), name='bill_detail'),
    url(r'^legislation/(?P<slug>[^/]+)/widget/$', NYCBillWidgetView.as_view(), name='bill_widget'),
    url(r'^legislation/(?P<slug>[^/]+)/rss/$', NYCBillDetailActionFeed(), name='bill_detail_action_feed'),
], settings.APP_NAME)

urlpatterns = [
    url(r'', include(patterns)),
    url(r'', include('councilmatic_core.urls')),
]

if (USING_NOTIFICATIONS):
    urlpatterns.extend([
        url(r'^login/$', notifications.views.notifications_login, name='notifications_login'),
        url(r'^logout/$', notifications.views.notifications_logout, name='notifications_logout'),
        url(r'^signup/$', notifications.views.notifications_signup, name='notifications_signup'),
        url(r'^account/settings/$', notifications.views.notifications_account_settings, name='notifications_account_settings'),
        url(r'^account/subscriptions/$', never_cache(notifications.views.SubscriptionsManageView.as_view()), name='subscriptions_manage'),
        url(r'^notification_loaddata$', notifications.views.notification_loaddata, name='notification_loaddata'),
        # list of things to subscribe/unsubscribe to:
        # - people
        # - committee actions
        # - committee events
        # - bill searches
        # - bill actions
        # - all events
        url(r'^person/(?P<slug>[^/]+)/subscribe/$', notifications.views.person_subscribe, name='person_subscribe'),
        url(r'^person/(?P<slug>[^/]+)/unsubscribe/$', notifications.views.person_unsubscribe, name='person_unsubscribe'),
        url(r'^legislation/(?P<slug>[^/]+)/subscribe/$', notifications.views.bill_subscribe, name='bill_subscribe'),
        url(r'^legislation/(?P<slug>[^/]+)/unsubscribe/$', notifications.views.bill_unsubscribe, name='bill_unsubscribe'),
        url(r'^committee/(?P<slug>[^/]+)/events/subscribe/$',
	    notifications.views.committee_events_subscribe, name='committee_events_subscribe'),
        url(r'^committee/(?P<slug>[^/]+)/events/unsubscribe/$',
	    notifications.views.committee_events_unsubscribe, name='committee_events_unsubscribe'),
        url(r'^committee/(?P<slug>[^/]+)/actions/subscribe/$',
	    notifications.views.committee_actions_subscribe, name='committee_actions_subscribe'),
        url(r'^committee/(?P<slug>[^/]+)/actions/unsubscribe/$',
	    notifications.views.committee_actions_unsubscribe, name='committee_actions_unsubscribe'),
        url(r'^search_check_subscription/$', notifications.views.search_check_subscription, name='search_check_subscription'),
        url(r'^search_subscribe/$', notifications.views.search_subscribe, name='search_subscribe'),
        url(r'^search_unsubscribe/$', notifications.views.search_unsubscribe, name='search_unsubscribe'),
        url(r'^events/subscribe/$',
	    notifications.views.events_subscribe, name='events_subscribe'),
        url(r'^events/unsubscribe/$',
	    notifications.views.events_unsubscribe, name='events_unsubscribe'),
        # django-rq: https://github.com/ui/django-rq
        url(r'^django-rq/', include('django_rq.urls')),
])
