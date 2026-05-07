// content.js - Scraper helper
console.log("Bhramos Scraper Content Script Active. Alt + Click any element to log its XPath.");

window.addEventListener('click', (e) => {
  if (e.altKey) {
    e.preventDefault();
    const xpath = getXPath(e.target);
    console.log("Selected XPath:", xpath);
    alert("Copied XPath: " + xpath);
    copyToClipboard(xpath);
  }
}, true);

function getXPath(element) {
  if (element.id !== '') return `//*[@id="${element.id}"]`;
  if (element === document.body) return element.tagName.toLowerCase();

  let ix = 0;
  const siblings = element.parentNode.childNodes;
  for (let i = 0; i < siblings.length; i++) {
    const sibling = siblings[i];
    if (sibling === element) return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) ix++;
  }
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    console.error('Failed to copy: ', err);
  }
}
