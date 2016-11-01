$(document).ready(function() {
    // For every anchor on the page, create an analytics track event onclick
    $('a').each(function(index, val){
        analytics.trackLink($(this), 'Clicked', {
            object: 'link',
            anchor_text:  $(this).text(),
            destination_url: $(this).attr("href"),
            page_name: window.location.pathname
        });
    });
});

// On form submit event, send analytics track event
$('form').submit(function( event ) {
    analytics.track('Form Submit', {
        form_id: $(this).attr("id")
    });
});
