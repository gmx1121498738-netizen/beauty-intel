(function () {
  var date = new URLSearchParams(window.location.search).get('date');
  if (!date) return;
  var node = document.querySelector('[data-date="' + date + '"]');
  if (node) node.classList.add('focus-date');
}());
