$(document).ready(function() {
    $('div.signup, .nav-tabs, .tab-content').show();
    $('#form-signup').submit(function(e) {
        var email_addr = $('#email').val();
        if (email_addr == '') {
            return false;
        }
        intercomSettings = {
            email: email_addr,
            created_at: Date.now() / 1000 | 0,
            app_id: "6f60bd754398773e9bb9976f4ca3e630d9fffeed"
        };
        $('#signup-content').fadeOut("slow", function() { $('#signup-content').html("<h1>Thanks for registering</h1><p>We'll be in touch soon.</p>").fadeIn("slow"); });
        window.Intercom('boot', intercomSettings); 
        return false;
    });
});
