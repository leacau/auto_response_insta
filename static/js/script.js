let currentPage = 1;
let selectedPostId = null;

document.addEventListener('DOMContentLoaded', function () {
	loadUserPosts(currentPage);

	// Paginación
	document.getElementById('prevPageBtn')?.addEventListener('click', () => {
		if (currentPage > 1) {
			currentPage--;
			loadUserPosts(currentPage);
		}
	});

	document.getElementById('nextPageBtn')?.addEventListener('click', () => {
		currentPage++;
		loadUserPosts(currentPage);
	});

	// Botón de volver
	document.getElementById('backToHomeBtn')?.addEventListener('click', () => {
		showScreen('screen-home');
	});

	// Cargar reglas cuando se hace clic en "Reglas"
	document
		.getElementById('screen-details')
		?.querySelectorAll('.tab-btn')
		.forEach((button) => {
			button.addEventListener('click', () => {
				const tab = button.getAttribute('data-tab');
				document
					.querySelectorAll('.tab-content')
					.forEach((content) => content.classList.remove('active'));
				document.getElementById(tab).classList.add('active');
			});
		});

	// Guardar nueva palabra clave
	document.getElementById('saveNewRuleBtn')?.addEventListener('click', () => {
		const post_id = document.getElementById('rulePostId').value.trim();
		const keyword = document.getElementById('ruleKeyword').value.trim();
		const responses = document.getElementById('ruleResponses').value.trim();

		if (!post_id || !keyword || !responses) {
			alert('Por favor completa todos los campos');
			return;
		}
		saveKeywordForPost(post_id, keyword, responses);
	});
});

function showScreen(screenId) {
	const screens = document.querySelectorAll('.screen');

	screens.forEach((s) => s.classList.remove('active'));
	document.getElementById(screenId).classList.add('active');

	// Si es la pantalla de detalles, cargar pestaña activa
	if (screenId === 'screen-details') {
		const firstTab = document
			.querySelector('.tab-btn.active')
			.getAttribute('data-tab');
		document
			.querySelectorAll('.tab-content')
			.forEach((c) => c.classList.remove('active'));
		document.getElementById(firstTab).classList.add('active');
	}
}

async function loadUserPosts(page = 1) {
	const container = document.getElementById('postSelectorContainer');
	container.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Cargando publicaciones...</p>';
	try {
		const response = await fetch(`/api/get_posts?page=${page}`);
		const data = await response.json();
		console.log('Datos de publicaciones:', data); // Debugging
		if (data.status === 'success') {
			container.innerHTML = '';
			const posts = data.posts || [];
			if (posts.length === 0) {
				container.innerHTML = '<p>No hay publicaciones disponibles.</p>';
				return;
			}
			posts.forEach((post) => {
				const div = document.createElement('div');
				div.className = 'post-item';
				div.dataset.id = post.id;
				div.innerHTML = `
                    <img src="${post.thumbnail}" width="100%" height="120" onerror="this.src='/static/images/placeholder.jpg'" />
                    <small>${post.caption}</small>
                `;
				div.addEventListener('click', () => {
					selectedPostId = post.id;
					loadPostDetails(post.id);
				});
				container.appendChild(div);
			});
			document.getElementById('prevPageBtn').disabled = page <= 1;
			document.getElementById('nextPageBtn').disabled = !data.has_next;
		} else {
			container.innerHTML = `<p class="error">Error: ${data.message}</p>`;
		}
	} catch (error) {
		container.innerHTML = `<p class="error">Error de conexión: ${error.message}</p>`;
	}
}

async function loadPostDetails(post_id) {
	const detailContainer = document.getElementById('responder');
	detailContainer.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Cargando detalles...</p>';

	try {
		const response = await fetch(`/api/post/${post_id}`);
		const data = await response.json();

		if (data.status === 'success') {
			const post = data.post;
			detailContainer.innerHTML = `
                <button id="backToHomeBtn" class="btn-back"><i class="fas fa-arrow-left"></i> Volver</button>
                <div class="post-detail">
                    <img id="detailThumbnail" src="${
											post.thumbnail
										}" width="100%" style="max-width: 400px; border-radius: 10px;" onerror="this.src="${
				post.url
			}"">
                    <div class="post-info">
                        <h3>Caption:</h3>
                        <p id="detailCaption">${post.caption}</p>
                        <h3>Likes:</h3>
                        <p id="detailLikes">${post.like_count}</p>
                        <h3>Comentarios:</h3>
                        <p id="detailComments">${post.comment_count}</p>
						<h3>Fecha:</h3>
						<p id="detailTimestamp">${
							post.timestamp
								? new Date(post.timestamp).toLocaleString()
								: 'Fecha no disponible'
						}</p>
                    </div>
                </div>`;

			// Actualizar el ID del post en Configuración
			document.getElementById('rulePostId').value = post.id;
			/* 
			// Mostrar datos del post en pestaña "Responder"
			const thumbnail = document.getElementById('detailThumbnail');
			thumbnail.src = post.thumbnail || '/static/images/placeholder.jpg';

			document.getElementById('detailCaption').textContent =
				post.caption || 'Sin descripción';
			document.getElementById('detailLikes').textContent = post.like_count || 0;
			document.getElementById('detailComments').textContent =
				post.comment_count || 0;
			document.getElementById('detailTimestamp').textContent = post.timestamp
				? new Date(post.timestamp).toLocaleString()
				: 'Fecha no disponible';

			*/

			// Mostrar pestaña de detalles
			showScreen('screen-details');

			// Añadir botón de procesar comentarios si no existe
			if (!document.getElementById('processCommentsBtn')) {
				const processBtn = document.createElement('button');
				processBtn.id = 'processCommentsBtn';
				processBtn.className = 'btn-primary';
				processBtn.innerHTML =
					'<i class="fas fa-robot"></i> Procesar Comentarios';
				processBtn.onclick = () => processPostComments(post.id);

				const configTab = document.getElementById('config');
				configTab.insertBefore(
					processBtn,
					document.getElementById('newRuleStatusBox')
				);
			}
		} else {
			detailContainer.innerHTML =
				'<p class="error">No se pudo cargar el post.</p>';
		}
	} catch (error) {
		detailContainer.innerHTML = `<p class="error">Error de conexión: ${error.message}</p>`;
	}
}

async function saveKeywordForPost(post_id, keyword, responses) {
	const statusBox = document.getElementById('newRuleStatusBox');
	statusBox.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Guardando regla...</p>';

	try {
		const response = await fetch('/api/add_rule', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ post_id, keyword, responses }),
		});

		const result = await response.json();

		if (result.status === 'success') {
			statusBox.innerHTML =
				'<p><i class="fas fa-check-circle"></i> Regla guardada con éxito</p>';
			document.getElementById('ruleKeyword').value = '';
			document.getElementById('ruleResponses').value = '';
			loadAllRules(post_id); // Recargar lista de reglas
		} else {
			statusBox.innerHTML = `<p class="error">Error: ${result.message}</p>`;
		}
	} catch (err) {
		statusBox.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
	}
}

async function loadAllRules(post_id = '') {
	const container = document.getElementById('rulesListContainer');
	container.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Cargando reglas guardadas...</p>';

	try {
		const response = await fetch('/api/list_rules');
		const data = await response.json();

		if (data.status === 'success') {
			container.innerHTML = '';
			const rules = data.rules || [];

			if (rules.length === 0) {
				container.innerHTML = '<p>No hay reglas definidas.</p>';
				return;
			}

			rules.forEach((rule) => {
				const div = document.createElement('div');
				div.className = 'keyword-rule';
				div.innerHTML = `
                    <strong>Publicación:</strong> ${rule.post_id}<br/>
                    <ul class="keyword-responses">
                        ${Object.entries(rule.keywords)
													.map(
														([k, rs]) =>
															`<li><strong>${k}:</strong> ${rs.join(', ')}</li>`
													)
													.join('')}
                    </ul>
                `;
				container.appendChild(div);
			});
		} else {
			container.innerHTML = `<p class="error">Error: ${data.message}</p>`;
		}
	} catch (error) {
		container.innerHTML = `<p class="error">Error de conexión: ${error.message}</p>`;
	}
}

async function loadHistory() {
	const historyList = document.getElementById('historyList');
	historyList.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Cargando historial...</p>';

	try {
		const response = await fetch('/api/get_history');
		const data = await response.json();

		if (data.status === 'success') {
			historyList.innerHTML = '';

			if (Object.keys(data.history).length === 0) {
				historyList.innerHTML =
					'<p>No hay historial de comentarios respondidos.</p>';
				return;
			}

			// Ordenar por fecha (más reciente primero)
			const sortedHistory = Object.entries(data.history).sort(
				(a, b) => new Date(b[1].fecha) - new Date(a[1].fecha)
			);

			sortedHistory.forEach(([id, item]) => {
				const historyItem = document.createElement('div');
				historyItem.className = 'history-item';
				if (item.matched) {
					historyItem.style.borderLeft = '4px solid #28a745';
				}

				historyItem.innerHTML = `
                    <p><strong>Usuario:</strong> ${item.usuario}</p>
                    <p><strong>Comentario:</strong> ${item.comentario}</p>
                    <p><strong>Respuesta:</strong> ${item.respuesta}</p>
                    <p><small>${new Date(
											item.fecha
										).toLocaleString()}</small></p>
                    ${
											item.matched
												? '<span class="matched-tag"><i class="fas fa-tag"></i> Palabra clave</span>'
												: ''
										}
                `;
				historyList.appendChild(historyItem);
			});
		} else {
			historyList.innerHTML = `<p class="error">Error: ${data.message}</p>`;
		}
	} catch (err) {
		historyList.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
	}
}

document.getElementById('historial').addEventListener('show', loadHistory);

async function processPostComments(post_id) {
	const statusBox = document.getElementById('newRuleStatusBox');
	statusBox.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Procesando comentarios...</p>';
	statusBox.className = 'status-box';

	try {
		const response = await fetch('/api/process_comments', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ post_id }),
		});

		const result = await response.json();

		if (result.status === 'success') {
			statusBox.innerHTML = `
                <p class="success">
                    <i class="fas fa-check-circle"></i> 
                    ${result.message}
                </p>
                <p>Nuevas respuestas: ${result.new_responses.length}</p>
            `;
			statusBox.classList.add('success');

			// Actualizar el historial
			if (document.getElementById('historial').classList.contains('active')) {
				loadHistory();
			}
		} else {
			statusBox.innerHTML = `<p class="error">Error: ${result.message}</p>`;
			statusBox.classList.add('error');
		}
	} catch (err) {
		statusBox.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
		statusBox.classList.add('error');
	}
}
