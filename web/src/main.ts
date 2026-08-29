import "@kit-ui/theme.css";
import "./app.css";
import { mount } from "svelte";
import App from "./App.svelte";

// Restore persisted dark-mode choice before first paint (kit-ui reads `.dark`
// on <html>). Default follows the OS.
try {
  const saved = localStorage.getItem("wg-theme");
  const dark = saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", dark);
} catch {
  /* private mode / storage blocked — fall back to light */
}

export default mount(App, { target: document.getElementById("app")! });
