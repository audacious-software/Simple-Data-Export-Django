# pylint: disable=no-member, too-few-public-methods

from django.contrib import admin

from .models import ReportJob, ReportDestination, ReportJobBatchRequest

def reset_report_jobs(modeladmin, request, queryset): # pylint: disable=unused-argument
    for job in queryset:
        job.started = None
        job.completed = None

        if job.report is not None:
            job.report.delete()
            job.report = None

        job.save()

reset_report_jobs.description = 'Reset report jobs'

@admin.register(ReportJob)
class ReportJobAdmin(admin.ModelAdmin):
    list_display = (
        'requester',
        'requested',
        'job_index',
        'job_count',
        'started',
        'completed'
    )

    list_filter = ('requested', 'started', 'completed',)

    actions = [reset_report_jobs]
    search_fields = ('parameters',)

@admin.register(ReportJobBatchRequest)
class ReportJobBatchRequestAdmin(admin.ModelAdmin):
    list_display = ('requester', 'requested', 'started', 'completed')
    list_filter = ('requested', 'started', 'completed', 'requester')

@admin.register(ReportDestination)
class ReportDestinationAdmin(admin.ModelAdmin):
    list_display = ('user', 'destination', 'description')
    search_fields = ('destination', 'user',)
