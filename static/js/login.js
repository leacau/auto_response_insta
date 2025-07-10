document.getElementById('loginBtn').addEventListener('click', async () => {
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value.trim();
  const status = document.getElementById('loginError');
  status.textContent = '';
  try {
    const userCred = await firebase.auth().signInWithEmailAndPassword(email, password);
    const idToken = await userCred.user.getIdToken();
    const res = await fetch('/sessionLogin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idToken })
    });
    if (res.ok) {
      window.location.href = '/';
    } else {
      const data = await res.json();
      status.textContent = data.message || 'Error de autenticaci\u00f3n';
    }
  } catch (err) {
    status.textContent = err.message;
  }
});
