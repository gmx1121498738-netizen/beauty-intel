(function () {
  var reports = window.__REPORTS__ || [];
  var resultNode = document.getElementById('search-results');
  var countNode = document.getElementById('search-count');
  var queryNode = document.getElementById('query');
  var dateNode = document.getElementById('report-date');
  var filters = Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));

  function esc(value) {
    return String(value).replace(/[&<>'"]/g, function (char) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char];
    });
  }
  function haystack(report) {
    return [report.title, report.summary].concat(report.dimensions, report.brands, report.categories, report.channels, report.event_types).join(' ').toLowerCase();
  }
  function matches(report) {
    var query = queryNode.value.trim().toLowerCase();
    if (query && haystack(report).indexOf(query) === -1) return false;
    if (dateNode.value && report.date !== dateNode.value) return false;
    return filters.every(function (node) {
      var value = node.value;
      return !value || (report[node.dataset.filter] || []).indexOf(value) !== -1;
    });
  }
  function render() {
    var visible = reports.filter(matches);
    countNode.textContent = '找到 ' + visible.length + ' 篇已发布报告';
    resultNode.innerHTML = visible.map(function (report) {
      return '<article class="search-result"><a href="' + esc(report.href) + '"><span class="meta">' + esc(report.kind === 'daily' ? '日报 · ' + report.date : '周报 · ' + report.week) + '</span><h2>' + esc(report.title) + '</h2><p>' + esc(report.summary) + '</p></a></article>';
    }).join('') || '<article class="search-result"><div style="padding:22px;color:#6b716b">没有匹配的已发布报告。</div></article>';
  }
  queryNode.addEventListener('input', render);
  dateNode.addEventListener('change', render);
  filters.forEach(function (node) { node.addEventListener('change', render); });
  render();
}());
