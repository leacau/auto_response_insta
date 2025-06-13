let currentPage = 1;
let selectedPostId = null;

document.addEventListener('DOMContentLoaded', function () {
	// Cargar publicaciones
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
		.forEach((s) => s.classList.remove('active'));
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
	const detailContainer = document.getElementById('postSelectorContainer');
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
                    <img src="${post.thumbnail}" 
                         width="100%" 
                         style="max-width: 400px; border-radius: 10px;"
                         onerror="this.src='/static/images/placeholder.jpg'" />
                    <div class="post-info">
                        <h3>Caption:</h3>
                        <p>${post.caption}</p>
                        <h3>Likes:</h3>
                        <p>${post.like_count}</p>
                        <h3>Comentarios:</h3>
                        <p>${post.comment_count}</p>
                        <h3>Agregar Palabra Clave</h3>
                        <input type="text" id="keywordInput" placeholder="Palabra clave...">
                        <textarea id="responseInput" rows="3" placeholder="Hasta 7 respuestas separadas por comas"></textarea>
                        <button id="saveKeywordBtn" class="btn-primary">Guardar</button>
                        <div id="detailStatusBox" class="status-box"></div>
                    </div>
                </div>
            `;

			// Reasignar eventos dinámicos
			document.getElementById('backToHomeBtn').addEventListener('click', () => {
				showScreen('screen-home');
			});

			document
				.getElementById('saveKeywordBtn')
				.addEventListener('click', () => {
					const keyword = document.getElementById('keywordInput').value.trim();
					const response = document
						.getElementById('responseInput')
						.value.trim();

					if (!keyword || !response) {
						alert('Completa ambos campos');
						return;
					}

					const responseList = response
						.split(',')
						.map((r) => r.trim())
						.filter(Boolean);

					if (responseList.length === 0) {
						alert('Por favor ingresa al menos una respuesta');
						return;
					}

					saveKeywordForPost(post.id, keyword, responseList);
				});

			showScreen('screen-detail');
		} else {
			detailContainer.innerHTML = `<p class="error">No se pudo cargar el post.</p>`;
		}
	} catch (error) {
		detailContainer.innerHTML = `<p class="error">Error de conexión: ${error.message}</p>`;
	}
}

async function saveKeywordForPost(post_id, keyword, response_list) {
	const statusBox = document.getElementById('detailStatusBox');
	statusBox.innerHTML =
		'<p><i class="fas fa-spinner fa-spin"></i> Guardando regla...</p>';

	try {
		const config = {
			keywords: { [keyword]: response_list },
			default_response: 'Gracias por tu comentario!',
		};

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
