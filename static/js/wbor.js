var SEARCH_DJ = "djcomplete"
var SEARCH_SHOW = "showcomplete"

function ajaxSearch(ajaxurl, query, callback) {
    return $.getJSON('/ajax/' + ajaxurl,
                     {'query': query},
                     callback);
}

var djbutton = $("<tr></tr>");
djbutton.append($("<td><a href=\"#\" id=\"remove-dj\">&times;</a></td>"));
djbutton.append($("<td id=\"djname\"></td>"));
djbutton.append($("<td id=\"djemail\">Email</td>"));
djbutton.append($("<input type=\"hidden\" id=\"djkey\""+
                  " name=\"djkey\" value=\"\"/>"));
djbutton.find("#remove-dj").click(function(e){
    alert("hi");
    $(this).parentsUntil(":not(td,tr)", "tr").remove();
    return false;
});

function addDjToProgram(key, name, email) {
    var newbutton = djbutton.clone();
    newbutton.find("#djname").text(name);
    newbutton.find("#djemail").text(email);
    newbutton.find("#djkey").val(key);

    $("#show-dj-list").find("tbody").append(newbutton);
    $("#dj-table").removeClass("hidden-djs");
    $("#no-dj-alert").addClass("hidden-djs");
    newbutton.find("#remove-dj").click(function(e){
        $(this).parentsUntil(":not(td,tr)", "tr").remove();
        return false;
    });
}
