$("#feedback").submit(function() {
    event.preventDefault();

    $.ajax({
        url: "https://www.formstack.com/forms/index.php",
        method: "POST",
        data: $("#feedback").serialize(),
        dataType: "json"
    });

    $("#feedback").html("<p>Thanks for your feedback, if you gave your email address we'll be in touch with you shortly.</p>");
});
