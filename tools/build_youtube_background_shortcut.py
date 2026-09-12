#!/usr/bin/env python3
import json
import os
import plistlib
import urllib.request

DONOR_ID = "0b61b78894ef45eb9699cc6b5681fa72"
NAME = "YouTube Background"
OUT = "dist/YouTube-Background.shortcut"

JS = r'''(() => {
  const KEY = '__cgptYoutubeBackgroundV1';
  const findVideo = () => document.querySelector('video');
  const initialVideo = findVideo();
  if (!initialVideo) { completion('No video found'); return; }

  if (window[KEY] && window[KEY].enable) {
    window[KEY].enable(initialVideo);
    initialVideo.play().catch(() => {});
    completion('Background playback enabled');
    return;
  }

  const DP = Document.prototype;
  const hiddenDescriptor = Object.getOwnPropertyDescriptor(DP, 'hidden');
  const realHidden = () => {
    try {
      return hiddenDescriptor && hiddenDescriptor.get
        ? !!hiddenDescriptor.get.call(document)
        : false;
    } catch (_) { return false; }
  };

  const state = {
    enabled: true,
    video: initialVideo,
    lastBackgroundSignal: 0,
    resuming: false,
    realHidden
  };
  window[KEY] = state;

  try { Object.defineProperty(DP, 'hidden', { configurable: true, get: () => false }); } catch (_) {}
  try { Object.defineProperty(DP, 'visibilityState', { configurable: true, get: () => 'visible' }); } catch (_) {}
  try { Object.defineProperty(DP, 'webkitHidden', { configurable: true, get: () => false }); } catch (_) {}
  try { Object.defineProperty(document, 'hasFocus', { configurable: true, value: () => true }); } catch (_) {}

  const originalPause = HTMLMediaElement.prototype.pause;

  const attach = (video) => {
    if (!video || video.__cgptBgAttached) return;
    video.__cgptBgAttached = true;
    video.setAttribute('playsinline', '');
    video.setAttribute('webkit-playsinline', '');

    video.addEventListener('pause', () => {
      const hidden = realHidden();
      const justBackgrounded = Date.now() - state.lastBackgroundSignal < 3500;
      if (!state.enabled || (!hidden && !justBackgrounded) || video.ended) return;
      resume(video);
    }, true);
  };

  const resume = (candidate) => {
    const video = candidate && candidate.isConnected ? candidate : findVideo();
    if (!video || video.ended || !state.enabled) return;
    state.video = video;
    attach(video);
    if (!video.paused || state.resuming) return;
    state.resuming = true;
    try {
      const p = video.play();
      if (p && typeof p.finally === 'function') {
        p.finally(() => { state.resuming = false; });
      } else {
        state.resuming = false;
      }
    } catch (_) {
      state.resuming = false;
    }
  };

  const backgroundSignal = () => {
    state.lastBackgroundSignal = Date.now();
    Promise.resolve().then(() => resume(state.video));
    setTimeout(() => resume(state.video), 60);
    setTimeout(() => resume(state.video), 300);
  };

  try {
    HTMLMediaElement.prototype.pause = function (...args) {
      if (state.enabled && this === state.video && realHidden()) return;
      return originalPause.apply(this, args);
    };
  } catch (_) {}

  document.addEventListener('visibilitychange', backgroundSignal, true);
  document.addEventListener('webkitvisibilitychange', backgroundSignal, true);
  window.addEventListener('pagehide', backgroundSignal, true);
  window.addEventListener('blur', backgroundSignal, true);
  document.addEventListener('freeze', backgroundSignal, true);

  const observer = new MutationObserver(() => {
    const video = findVideo();
    if (video && video !== state.video) {
      state.video = video;
      attach(video);
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  state.enable = (video) => {
    state.enabled = true;
    state.video = video || findVideo();
    attach(state.video);
  };

  attach(initialVideo);
  initialVideo.play().catch(() => {});
  completion('Background playback enabled');
})();'''


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_donor():
    meta = get_json(f"https://www.icloud.com/shortcuts/api/records/{DONOR_ID}")
    rec = meta.get("records", [meta])[0]
    fields = rec["fields"]
    url = fields["shortcut"]["value"]["downloadURL"].replace("${f}", "donor.shortcut")
    return plistlib.loads(get_bytes(url))


def sign_with_hubsign(shortcut):
    xml = plistlib.dumps(shortcut, fmt=plistlib.FMT_XML).decode("utf-8")
    body = json.dumps({"shortcutName": NAME, "shortcut": xml}).encode("utf-8")
    req = urllib.request.Request(
        "https://hubsign.routinehub.services/sign",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "cherri/1.0",
            "Origin": "https://routinehub.co",
            "Referer": "https://routinehub.co/",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if data[:4] != b"AEA1":
        raise RuntimeError(f"Signing failed: response starts {data[:16]!r}")
    return data


def main():
    donor = fetch_donor()
    actions = donor.get("WFWorkflowActions", [])
    js_actions = [a for a in actions if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.runjavascriptonwebpage"]
    if not js_actions:
        raise RuntimeError("Donor shortcut has no Run JavaScript on Web Page action")

    action = js_actions[0]
    action.setdefault("WFWorkflowActionParameters", {})["WFJavaScript"] = JS

    donor["WFWorkflowActions"] = [action]
    donor["WFWorkflowName"] = NAME
    donor["WFWorkflowTypes"] = ["ActionExtension"]
    donor["WFWorkflowInputContentItemClasses"] = ["WFSafariWebPageContentItem"]
    donor["WFWorkflowOutputContentItemClasses"] = []
    donor["WFWorkflowHasShortcutInputVariables"] = True
    donor["WFWorkflowHasOutputFallback"] = False
    donor["WFWorkflowImportQuestions"] = []

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    signed = sign_with_hubsign(donor)
    with open(OUT, "wb") as f:
        f.write(signed)
    print(f"Wrote {OUT}: {len(signed)} bytes, magic={signed[:4]!r}")


if __name__ == "__main__":
    main()
