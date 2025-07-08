// Variables globales
let currentPage = 1;
let selectedPostId = null;

// Inicialización al cargar la página
document.addEventListener("DOMContentLoaded", function () {
  loadUserPosts(currentPage);

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

  // Guardar nueva palabra clave
  document.getElementById("saveNewRuleBtn")?.addEventListener("click", () => {
    const post_id = document.getElementById("rulePostId").value.trim();
    const keyword = document.getElementById("ruleKeyword").value.trim();
    const responses = document.getElementById("ruleResponses").value.trim();
    
    if (!keyword || !responses) {
      alert("Por favor completa ambos campos");
      return;
    }
    
    saveKeywordForPost(post_id, keyword, responses);
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
});

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
        
        div.addEventListener("click", () => {
          selectedPostId = post.id;
          loadPostDetails(post.id);
        });
        
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
  responderContainer.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Cargando detalles del post...</p>';
  
  try {
    const response = await fetch(`/api/post/${post_id}`);
    const data = await response.json();
    
    if (data.status === "success") {
      const post = data.post;
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
            commentDiv.innerHTML = `
              <strong>${comment.username}</strong>: "${comment.text}"
              <small>${new Date(comment.timestamp).toLocaleString()}</small>
            `;
            commentsList.appendChild(commentDiv);
          });
        }
      }
    }
  } catch (err) {
    responderContainer.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
  }
}

// Guardar una nueva regla
async function saveKeywordForPost(post_id, keyword, responses) {
  const statusBox = document.getElementById("newRuleStatusBox");
  statusBox.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> Guardando regla...</p>';
  
  const responseArray = responses
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
          // Verificación segura de rule.keywords
          if (rule.keywords && typeof rule.keywords === "object") {
            Object.entries(rule.keywords).forEach(([key, responses]) => {
              const ruleDiv = document.createElement("div");
              ruleDiv.className = "keyword-rule";
              ruleDiv.innerHTML = `
                <strong>${key}:</strong>
                <ul>
                  ${responses.map((resp) => `<li>"${resp}"</li>`).join("")}
                </ul>
              `;
              rulesContainer.appendChild(ruleDiv);
            });
          }
        }
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
