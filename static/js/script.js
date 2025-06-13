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
});

function showScreen(screenId) {
	document
		.querySelectorAll('.screen')
		.forEach((screen) => screen.classList.remove('active'));
	document.getElementById(screenId).classList.add('active');
}

async function loadUserPosts(page = 1) {
	const container = document.getElementById('postSelectorContainer');
	container.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Cargando publicaciones...</p>';

	try {
		const response = await fetch(`/api/get_posts?page=${page}`);
		const data = await response.json();

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
	const detailContainer = document.getElementById('postDetail');
	detailContainer.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Cargando detalles...</p>';

	try {
		const response = await fetch(`/api/post/${post_id}`);
		const data = await response.json();

		if (data.status === 'success') {
			const post = data.post;

			detailContainer.innerHTML = `
                <button id="backToHomeBtn" class="btn-back">
                    <i class="fas fa-arrow-left"></i> Volver
                </button>
                <h3>Caption:</h3>
                <p id="detailCaption">${post.caption}</p>
                <p><strong>Likes:</strong> <span id="detailLikes">${
									post.like_count
								}</span></p>
                <p><strong>Comentarios:</strong> <span id="detailComments">${
									post.comment_count
								}</span></p>
                <p><small id="detailTimestamp">${new Date(
									post.timestamp
								).toLocaleString()}</small></p>
                <h3>Miniatura:</h3>
                <img id="detailThumbnail" src="${post.thumbnail}" 
                     style="max-width: 400px; border-radius: 10px;" 
                     onerror="this.src='/static/images/placeholder.jpg'">
                <div id="keywordForm">
                    <h3>Agregar Palabra Clave</h3>
                    <input type="text" id="keywordInput" placeholder="Ejemplo: hola...">
                    <textarea id="responseInput" rows="3" placeholder="Respuesta..."></textarea>
                    <button id="saveKeywordBtn" class="btn-primary">Guardar</button>
                    <div id="detailStatusBox" class="status-box"></div>
                </div>
            `;

			// Reasignar evento al botón de volver
			document.getElementById('backToHomeBtn').addEventListener('click', () => {
				showScreen('screen-home');
			});

			// Agregar evento al botón de guardar palabra clave
			document
				.getElementById('saveKeywordBtn')
				.addEventListener('click', () => {
					const keyword = document.getElementById('keywordInput').value.trim();
					const response = document
						.getElementById('responseInput')
						.value.trim();

					if (!keyword || !response) {
						alert('Por favor completa ambos campos');
						return;
					}

					saveKeywordForPost(post.id, keyword, response);
				});

			showScreen('screen-details');
		} else {
			detailContainer.innerHTML = `<p class="error">No se pudo cargar el post.</p>`;
		}
	} catch (error) {
		detailContainer.innerHTML = `<p class="error">Error de conexión: ${error.message}</p>`;
	}
}

async function saveKeywordForPost(post_id, keyword, response_text) {
	const statusBox = document.getElementById('detailStatusBox');
	statusBox.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Guardando palabra clave...</p>';

	try {
		const config = load_config(post_id) || {};
		config.keywords = config.keywords || {};
		config.keywords[keyword] = [response_text];

		const res = await fetch('/api/save_keyword', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ post_id, config }),
		});

		const result = await res.json();

		if (result.status === 'success') {
			statusBox.innerHTML =
				'<p><i class="fas fa-check-circle"></i> Regla guardada con éxito</p>';
		} else {
			statusBox.innerHTML = `<p class="error">Error: ${result.message}</p>`;
		}
	} catch (err) {
		statusBox.innerHTML = `<p class="error">Error de conexión: ${err.message}</p>`;
	}
}
