if (!(window.location.host).startsWith("www.amazon.")) {
	alert("This bookmarklet must be run on an Amazon site!")
} else {
	var previousCount = -1;
	var unchangedCount = 0;
	var checkExist = setInterval(function () {
        var items = document.querySelectorAll(".g-item-sortable");
		if (document.getElementById("endOfListMarker") || unchangedCount >= 3) {
			clearInterval(checkExist);
			const a = document.createElement('a');
			const file = new Blob([document.getElementById('wishlist-page').outerHTML], {
				type: 'text/html'
			});

			var filename = window.location.host + "_" + document.getElementById("listId").value + "_" + opts.language + '.html'

			a.href = URL.createObjectURL(file);
			a.download = filename;
			a.click();

			URL.revokeObjectURL(a.href);
		} else {
			if (items.length === previousCount) {
				unchangedCount++;
			} else {
				unchangedCount = 0;
			}
			previousCount = items.length;
			last = items[items.length - 1];
			last.scrollIntoView();
		}
	}, 2000);
}