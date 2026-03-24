// Make table rows clickable by navigating to the first link in the row
document.addEventListener('DOMContentLoaded', function() {
  // Find all table rows in the main content
  const tableRows = document.querySelectorAll('.md-typeset table tbody tr');

  tableRows.forEach(row => {
    // Find the first link in the row
    const link = row.querySelector('a');

    if (link) {
      // Make the row clickable
      row.addEventListener('click', function(e) {
        // Only navigate if clicking on the row itself, not on a link
        // (to prevent double navigation)
        if (e.target.tagName !== 'A') {
          window.location.href = link.href;
        }
      });
    }
  });
});
