chrome.action.onClicked.addListener(() => {
    chrome.windows.create({
      url: 'popup.html',
      type: 'popup', // A normal window is resizable by default
      width: 400,
      height: 600,
      focused: true
    });
  });
  