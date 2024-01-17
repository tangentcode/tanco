
// Import the functions you need from the SDKs you need
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import {
  getAuth,
  signInWithRedirect,
  signOut as signOut0,
  GithubAuthProvider,
  GoogleAuthProvider,
  getRedirectResult
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth.js"

import { firebaseConfig } from "./firebase-cfg.mjs";

const _app = initializeApp(firebaseConfig);
const auth = getAuth();
await auth.authStateReady();


// encapsulate the important bits of firebase auth:
function currentUser() { return auth.currentUser }
function signOut() { return signOut0(auth) }

async function attemptLogin(how, onLoginSuccess) {
  let provider = null;
  switch(how) {
    // TODO: case 'github': provider = new GithubAuthProvider(); break;
    case 'google': provider = new GoogleAuthProvider(); break;
    default: console.log('no provider specified'); return; }
  await signInWithRedirect(auth, provider);
  await getRedirectResult(auth);
  if (auth.currentUser) { onLoginSuccess() }
  else { alert('login failed')}}

export {
  currentUser,
  signOut,
  attemptLogin };
