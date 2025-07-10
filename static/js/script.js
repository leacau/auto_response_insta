// Variables globales
let currentPage = 1;
let selectedPostId = null;
let keywordsBuffer = [];
let responsesBuffer = [];
let globalKeywordsBuffer = [];
let globalResponsesBuffer = [];

// Inicialización al cargar la página
document.addEventListener("DOMContentLoaded", function () {
  loadUserPosts(currentPage);

  document.getElementById("logoutBtn")?.addEventListener("click", async () => {
    try {
      await firebase.auth().signOut();
    } catch (e) {}
    await fetch("/sessionLogout", { method: "POST" });
    window.location.href = "/login";
  });

  const selector = document.getElementById("postSelectorContainer");
  selector?.addEventListener("click", (e) => {
    const item = e.target.closest(".post-item");
    if (item) {
      selectedPostId = item.dataset.id;
      loadPostDetails(item.dataset.id);
    }
  });

  // Paginación
  document.getElementById("prevPageBtn")?.addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage--;
      loadUserPosts(currentPage);
    }
  });

  document.getElementById("nextPageBtn")?.addEventListener("click", () => {
    currentPage++;
    loadUserPosts(currentPage);
  });

  // Botón "Volver"
  document.getElementById("backToHomeBtn")?.addEventListener("click", () => {
    showScreen("screen-home");
  });

  document.getElementById("ruleKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const v = e.target.value.trim();
      if (v && !keywordsBuffer.includes(v)) {
        keywordsBuffer.push(v);
        e.target.value = "";
        renderKeywordChips();
      }
    }
  });

  document
    .getElementById("ruleResponseInput")
    ?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const v = e.target.value.trim();
        if (v && !responsesBuffer.includes(v)) {
          responsesBuffer.push(v);
          e.target.value = "";
          renderResponseChips();
        }
      }
    });

  // Guardar nueva palabra clave
  document.getElementById("saveNewRuleBtn")?.addEventListener("click", async () => {
    const post_id = document.getElementById("rulePostId").value.trim();
    if (!post_id) return;
    if (keywordsBuffer.length === 0 || responsesBuffer.length === 0) {
      alert("Debes ingresar al menos una palabra clave y una respuesta");
      return;
    }
    for (const kw of keywordsBuffer) {
      await saveKeywordForPost(post_id, kw, responsesBuffer);
    }
    keywordsBuffer = [];
    responsesBuffer = [];
    renderKeywordChips();
    renderResponseChips();
  });

  document.getElementById("globalRuleKeyword")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const v = e.target.value.trim();
      if (v && !globalKeywordsBuffer.includes(v)) {
        globalKeywordsBuffer.push(v);
        e.target.value = "";
        renderGlobalKeywordChips();
      }
    }
  });

  document
    .getElementById("globalRuleResponseInput")
    ?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const v = e.target.value.trim();
        if (v && !globalResponsesBuffer.includes(v)) {
          globalResponsesBuffer.push(v);
          e.target.value = "";
          renderGlobalResponseChips();
        }
      }
    });

  document.getElementById("saveDmMessageBtn")?.addEventListener("click", () => {
    const post_id = document.getElementById("rulePostId").value.trim();
    const dm_message = document.getElementById("dmMessage").value.trim();
    const button_text = document.getElementById("dmButtonText").value.trim();
    const button_url = document.getElementById("dmButtonUrl").value.trim();
    if (!post_id) return;
    saveDmMessage(post_id, dm_message, button_text, button_url);
  });

  // Mostrar política de privacidad
  document.getElementById("privacyBtn")?.addEventListener("click", () => {
    showScreen("screen-privacy");
  });

  document.getElementById("backFromPrivacyBtn")?.addEventListener("click", () => {
    const previous = 
      document.querySelector(".screen.active").id === "screen-details" 
        ? "screen-details" 
        : "screen-home";
    showScreen(previous);
  });

  initializeAutoToggle();
  initEmojiBars();
  renderKeywordChips();
  renderResponseChips();
  renderGlobalKeywordChips();
  renderGlobalResponseChips();

  // Configuración de pestañas
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
      // Quitar clase 'active' de todos los botones y pestañas
      document.querySelectorAll(".tab-btn").forEach((btn) => btn.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((content) => content.classList.remove("active"));
      
      // Usar dataset para obtener el tab (corrección principal)
      const tab = button.dataset.tab;
      button.classList.add("active");
      document.getElementById(tab).classList.add("active");
    });
  });

  // Al iniciar, ocultar/mostrar campos según estado del toggle
  toggleRuleFields(document.getElementById("autoToggle")?.checked);
});

function showScreen(screenId) {
  document.querySelectorAll(".screen").forEach((screen) => screen.classList.remove("active"));
  const target = document.getElementById(screenId);
  if (target) {
    target.classList.add("active");
  }
}

function toggleRuleFields(enabled) {
    // Lista de IDs de campos a deshabilitar
    const fieldIds = [
        'ruleKeyword', 
        'ruleResponseInput',
        'saveNewRuleBtn',
        'dmMessage',
        'dmButtonText',
        'dmButtonUrl',
        'saveDmMessageBtn',
        'testComment',
        'runTestBtn'
    ];
    
    fieldIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = !enabled;
    });
}

function renderKeywordChips() {
  const container = document.getElementById("keywordList");
  if (!container) return;
  container.innerHTML = "";
  keywordsBuffer.forEach((kw, idx) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${kw} <button data-idx="${idx}">&times;</button>`;
    container.appendChild(chip);
  });
  container.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      keywordsBuffer.splice(btn.dataset.idx, 1);
      renderKeywordChips();
    });
  });
}

function renderResponseChips() {
  const container = document.getElementById("responseList");
  if (!container) return;
  container.innerHTML = "";
  responsesBuffer.forEach((resp, idx) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${resp} <button data-idx="${idx}">&times;</button>`;
    container.appendChild(chip);
  });
  container.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      responsesBuffer.splice(btn.dataset.idx, 1);
      renderResponseChips();
    });
  });
}

function renderGlobalKeywordChips() {
  const container = document.getElementById("globalKeywordList");
  if (!container) return;
  container.innerHTML = "";
  globalKeywordsBuffer.forEach((kw, idx) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${kw} <button data-idx="${idx}">&times;</button>`;
    container.appendChild(chip);
  });
  container.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      globalKeywordsBuffer.splice(btn.dataset.idx, 1);
      renderGlobalKeywordChips();
    });
  });
}

function renderGlobalResponseChips() {
  const container = document.getElementById("globalResponseList");
  if (!container) return;
  container.innerHTML = "";
  globalResponsesBuffer.forEach((resp, idx) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${resp} <button data-idx="${idx}">&times;</button>`;
    container.appendChild(chip);
  });
  container.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      globalResponsesBuffer.splice(btn.dataset.idx, 1);
      renderGlobalResponseChips();
    });
  });
}

function initEmojiBars() {
  document.querySelectorAll(".emoji-bar").forEach((bar) => {
    const target = document.getElementById(bar.dataset.target);
    if (!target) return;
    bar.querySelectorAll("span").forEach((sp) => {
      sp.addEventListener("click", () => insertAtCursor(target, sp.textContent));
    });
  });
}

function insertAtCursor(input, text) {
  const start = input.selectionStart;
  const end = input.selectionEnd;
  input.value = input.value.substring(0, start) + text + input.value.substring(end);
  input.selectionStart = input.selectionEnd = start + text.length;
  input.focus();
}

function initializeAutoToggle() {
  const toggle = document.getElementById("autoToggle");
  if (!toggle) return;
  toggle.addEventListener("change", async () => {
    const post_id = document.getElementById("rulePostId").value.trim();
    const enabled = toggle.checked;
    toggleRuleFields(enabled);
    if (!post_id) return;
    try {
      await fetch("/api/set_auto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ post_id, enabled }),
      });
    } catch (e) {
      console.error("Error actualizando auto", e);
    }
  });
}

// Cargar publicaciones del usuario
async function loadUserPosts(page = 1) {
  const container = document.getElementById("postSelectorContainer");
  container.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Cargando publicaciones...</p>';
  
  try {
    const response = await fetch(`/api/get_posts?page=${page}`);
    const data = await response.json();
    
    if (data.status === "success") {
      container.innerHTML = "";
      const posts = data.posts || [];
      
      if (posts.length === 0) {
        container.innerHTML = "<p>No hay publicaciones disponibles.</p>";
        return;
      }
      
      posts.forEach((post) => {
        const div = document.createElement("div");
        div.className = "post-item";
        div.dataset.id = post.id;
        div.innerHTML = `
          <img src="${post.thumbnail}" width="100%" height="120" onerror="this.src='/static/images/placeholder.jpg'" />
          <small>${post.caption}</small>
        `;
        
        
        container.appendChild(div);
      });
      
      document.getElementById("prevPageBtn").disabled = page <= 1;
      document.getElementById("nextPageBtn").disabled = !(data.has_next || false);
    } else {
      container.innerHTML = `<p class="error">Error: ${data.message}</p>`;
    }
  } catch (err) {
    container.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}

// Cargar detalles de una publicación
async function loadPostDetails(post_id) {
  const responderContainer = document.getElementById("responder");
  showScreen("screen-details");
  responderContainer.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Cargando detalles del post...</p>';
  
  try {
    const response = await fetch(`/api/post/${post_id}`);
    const data = await response.json();
    
    if (data.status === "success") {
      const post = data.post;
      showScreen("screen-details");
      responderContainer.innerHTML = `
        <h2>Detalles del Post</h2>
        <img id="detailThumbnail" src="${post.thumbnail || "/static/images/placeholder.jpg"}" width="100%" height="200" onerror="this.src='/static/images/placeholder.jpg'" />
        <p id="detailCaption">${post.caption || "Sin descripción"}</p>
        <p><strong>Likes:</strong> <span id="detailLikes">${post.like_count || 0}</span></p>
        <p><strong>Comentarios:</strong> <span id="detailComments">${post.comment_count || 0}</span></p>
        <p><strong>Fecha:</strong> <span id="detailTimestamp">${new Date(post.timestamp).toLocaleString()}</span></p>
        <div id="commentsList">
          <p><i class="fas fa-spinner fa-spin"></i> Cargando comentarios...</p>
        </div>
      `;
      
      // Asignar ID del post a los campos de regla
      document.getElementById("rulePostId").value = post_id;
      
      // Activar switch y campos
      const autoToggle = document.getElementById("autoToggle");
      if (autoToggle) {
        autoToggle.checked = post.enabled || false;
        toggleRuleFields(autoToggle.checked);
      }

      if (document.getElementById("dmMessage")) {
        document.getElementById("dmMessage").value = post.dm_message || "";
      }
      if (document.getElementById("dmButtonText")) {
        document.getElementById("dmButtonText").value = post.dm_button_text || "";
      }
      if (document.getElementById("dmButtonUrl")) {
        document.getElementById("dmButtonUrl").value = post.dm_button_url || "";
      }
      
      // Asignar ID del post a los campos de prueba
      document.getElementById("testPostId").value = post_id;
      
      // Cargar comentarios del post
      const commentsList = document.getElementById("commentsList");
      const commentResponse = await fetch(`/api/comments/${post_id}`);
      const commentData = await commentResponse.json();
      
      if (commentData.status === "success") {
        commentsList.innerHTML = "";
        const comments = commentData.comments || [];
        document.getElementById("detailComments").textContent = commentData.total;
        
        if (comments.length === 0) {
          commentsList.innerHTML = "<p>No hay comentarios aún.</p>";
        } else {
          comments.forEach((comment) => {
            const commentDiv = document.createElement("div");
            commentDiv.className = "comment-item";

            const header = document.createElement("div");
            header.innerHTML = `
              <strong class="comment-user">${comment.username} (${comment.user_id} - ${comment.id})</strong>
              <p class="comment-text">"${comment.text}"</p>
              <small class="comment-date">${new Date(comment.timestamp).toLocaleString()}</small>
            `;
            commentDiv.appendChild(header);

            if (comment.comment_count && comment.comment_count > 0) {
              const toggleBtn = document.createElement("button");
              toggleBtn.textContent = `Ver respuestas (${comment.comment_count})`;
              toggleBtn.className = "btn-toggle-replies";

              const repliesContainer = document.createElement("div");
              repliesContainer.className = "replies-container";
              repliesContainer.style.display = "none";

              toggleBtn.addEventListener("click", async () => {
                if (repliesContainer.style.display === "none") {
                  toggleBtn.textContent = "Ocultar respuestas";
                  repliesContainer.style.display = "block";
                  if (!repliesContainer.dataset.loaded) {
                    repliesContainer.innerHTML = `<p><i class='fas fa-spinner fa-spin'></i> Cargando...</p>`;
                    try {
                      const res = await fetch(`/api/replies/${comment.id}`);
                      const data = await res.json();
                      if (data.status === "success") {
                        repliesContainer.innerHTML = "";
                        const replies = data.replies || [];
                        if (replies.length === 0) {
                          repliesContainer.innerHTML = "<p>No hay respuestas.</p>";
                        } else {
                          replies.forEach((rep) => {
                            const repDiv = document.createElement("div");
                            repDiv.className = "reply-item";
                            repDiv.innerHTML = `
                              <strong class="comment-user">${rep.username} (${rep.user_id})</strong>
                              <p class="comment-text">"${rep.text}"</p>
                              <small class="comment-date">${new Date(rep.timestamp).toLocaleString()}</small>
                            `;
                            repliesContainer.appendChild(repDiv);
                          });
                        }
                        repliesContainer.dataset.loaded = "true";
                      } else {
                        repliesContainer.innerHTML = `<p class='error'>${data.message || 'Error'}</p>`;
                      }
                    } catch (err) {
                      repliesContainer.innerHTML = `<p class='error'>${err.message}</p>`;
                    }
                  }
                } else {
                  repliesContainer.style.display = "none";
                  toggleBtn.textContent = `Ver respuestas (${comment.comment_count})`;
                }
              });

              commentDiv.appendChild(toggleBtn);
              commentDiv.appendChild(repliesContainer);
            }

            commentsList.appendChild(commentDiv);
          });
        }
      }

      await loadAllRules(post_id);
      await loadAllRulesForTest(post_id);
    }
  } catch (err) {
    responderContainer.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}

// Guardar una nueva regla
async function saveKeywordForPost(post_id, keyword, responses) {
  const statusBox = document.getElementById("newRuleStatusBox");
  statusBox.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Guardando regla...</p>';
  
  const responseArray = Array.isArray(responses)
    ? responses
    : responses
        .split(",")
        .map((r) => r.trim())
        .filter(Boolean);
  
  if (responseArray.length === 0) {
    statusBox.innerHTML = `<p class="error">Debes ingresar al menos una respuesta</p>`;
    return;
  }
  
  if (responseArray.length > 7) {
    statusBox.innerHTML = `<p class="error">Máximo 7 respuestas por palabra clave</p>`;
    return;
  }
  
  try {
    const res = await fetch("/api/add_rule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ post_id, keyword, responses }),
    });
    
    const result = await res.json();
    
    if (result.status === "success") {
      statusBox.innerHTML = `<p class="success"><i class="fas fa-check-circle"></i> Regla guardada con éxito</p>`;
      setTimeout(() => (statusBox.innerHTML = ""), 3000);
      await loadAllRules(post_id); // Recargar reglas para este post
    } else {
      statusBox.innerHTML = `<p class="error">Error: ${result.message}</p>`;
    }
  } catch (err) {
    statusBox.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}

// Cargar todas las reglas
async function loadAllRules(post_id = null) {
  const rulesContainer = document.getElementById("configRulesListContainer");
  rulesContainer.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Cargando reglas...</p>';
  
  try {
    const response = await fetch("/api/list_rules");
    const data = await response.json();
    
    if (data.status === "success") {
      rulesContainer.innerHTML = "";
      const rules = data.rules || [];
      
      if (rules.length === 0) {
        rulesContainer.innerHTML = "<p>No hay reglas definidas.</p>";
        return;
      }
      
      rules.forEach((rule) => {
        if (!post_id || rule.post_id === post_id) {
          if (rule.keywords && typeof rule.keywords === "object") {
            Object.entries(rule.keywords).forEach(([key, responses]) => {
              const ruleDiv = document.createElement("div");
              ruleDiv.className = "keyword-rule";
              ruleDiv.innerHTML = `
                <div class="keyword-header">
                  <strong>${key}</strong>
                  <button class="delete-rule-btn" data-post="${rule.post_id}" data-key="${key}"><i class="fas fa-trash"></i></button>
                </div>
                <ul>
                  ${responses.map((resp) => `<li>${resp}</li>`).join("")}
                </ul>
              `;
              rulesContainer.appendChild(ruleDiv);
            });
          }
        }
      });

      document.querySelectorAll(".delete-rule-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const p = btn.dataset.post;
          const k = btn.dataset.key;
          if (!confirm(`Eliminar la palabra "${k}"?`)) return;
          try {
            const res = await fetch("/api/delete_rule", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ post_id: p, keyword: k }),
            });
            const r = await res.json();
            if (r.status === "success") {
              loadAllRules(post_id);
            } else {
              alert("Error: " + r.message);
            }
          } catch (e) {
            alert("Error: " + e.message);
          }
        });
      });
    } else {
      rulesContainer.innerHTML = `<p class="error">Error: ${data.message}</p>`;
    }
  } catch (err) {
    rulesContainer.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}

// Ejecutar prueba manual
document.getElementById("runTestBtn")?.addEventListener("click", () => {
  const post_id = document.getElementById("testPostId").value.trim();
  const comment_text = document.getElementById("testComment").value.trim();
  
  if (!post_id || !comment_text) {
    alert("Por favor completa ambos campos");
    return;
  }
  
  runManualTest(post_id, comment_text);
});

// Función para prueba manual
async function runManualTest(post_id, comment_text) {
  const resultBox = document.getElementById("testResultBox");
  resultBox.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Ejecutando...</p>';
  
  try {
    const response = await fetch("/api/process_comments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ post_id, comment_text }),
    });
    
    const result = await response.json();
    
    if (result.status === "success") {
      resultBox.innerHTML = `
        <div class="success-message">
          <strong>Resultado:</strong><br/>
          Coincidencia: ${result.matched ? "Sí" : "No"}<br/>
          Respuesta: "${result.response}"
        </div>
      `;
    } else {
      resultBox.innerHTML = `<p class="error">Error: ${result.message}</p>`;
    }
  } catch (err) {
    resultBox.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}

// Cargar reglas para la pestaña de prueba
async function loadAllRulesForTest(post_id = null) {
  const container = document.getElementById("rulesListContainer");
  container.innerHTML = "<p>Cargando reglas...</p>";
  
  try {
    const response = await fetch("/api/list_rules");
    const data = await response.json();
    
    if (data.status === "success") {
      container.innerHTML = "";
      const rules = data.rules || [];
      
      if (rules.length === 0) {
        container.innerHTML = "<p>No hay reglas definidas.</p>";
        return;
      }
      
      rules.forEach((rule) => {
        if (!post_id || rule.post_id === post_id) {
          const div = document.createElement("div");
          div.className = "keyword-rule";
          div.innerHTML = `
            <strong>Post ID:</strong> ${rule.post_id}<br/>
            <ul>
              ${Object.entries(rule.keywords)
                .map(
                  ([key, responses]) =>
                    `<li><strong>${key}:</strong> ${responses.join(", ")}</li>`
                )
                .join("")}
            </ul>
          `;
          container.appendChild(div);
        }
      });
    } else {
      container.innerHTML = `<p class="error">Error: ${data.message}</p>`;
    }
  } catch (err) {
    container.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}

// Guardar mensaje directo
async function saveDmMessage(post_id, dm_message, button_text, button_url) {
  const statusBox = document.getElementById("dmStatusBox");
  statusBox.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Guardando mensaje...</p>';
  try {
    const res = await fetch("/api/set_dm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ post_id, dm_message, button_text, button_url }),
    });
    const result = await res.json();
    if (result.status === "success") {
      statusBox.innerHTML = '<p class="success"><i class="fas fa-check-circle"></i> Mensaje guardado</p>';
      setTimeout(() => (statusBox.innerHTML = ""), 3000);
    } else {
      statusBox.innerHTML = `<p class="error">Error: ${result.message}</p>`;
    }
  } catch (err) {
    statusBox.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}
