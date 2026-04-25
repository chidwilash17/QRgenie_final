from django.urls import path
from apps.core.views import UserListView, UserDetailView, InviteMemberView, AcceptInvitationView

urlpatterns = [
    path('', UserListView.as_view(), name='user-list'),
    path('<uuid:id>/', UserDetailView.as_view(), name='user-detail'),
    path('invite/', InviteMemberView.as_view(), name='user-invite'),
    path('accept-invite/', AcceptInvitationView.as_view(), name='user-accept-invite'),
]
