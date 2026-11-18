const rows = document.querySelector('#rows');
const filter = document.querySelector('#filter');
let records = [];
function render() {
  rows.replaceChildren();
  for (const record of records.filter(r => filter.value === 'all' || r.evidence === filter.value)) {
    const row = document.createElement('tr');
    for (const value of [record.name, record.category, record.calls, record.evidence]) {
      const cell = document.createElement('td'); cell.textContent = String(value); row.append(cell);
    }
    rows.append(row);
  }
}
filter.addEventListener('change', render);
fetch('data/demo.json').then(r => { if (!r.ok) throw new Error('Fixture unavailable'); return r.json(); }).then(data => {
  if (data.synthetic !== true) throw new Error('This sketch only accepts synthetic data');
  records = data.workflows; render();
}).catch(error => { document.querySelector('#status').textContent = error.message + '. Serve this directory over HTTP using the README command.'; });
