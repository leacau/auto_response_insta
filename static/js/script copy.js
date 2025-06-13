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

	// Regresar a inicio
	document.getElementById('backToHomeBtn')?.addEventListener('click', () => {
		showScreen('screen-home');
	});

	// Guardar palabra clave
	document.getElementById('saveKeywordBtn')?.addEventListener('click', () => {
		const keyword = document.getElementById('keywordInput').value.trim();
		const response = document.getElementById('responseInput').value.trim();

		if (!keyword || !response) {
			alert('Por favor completa ambos campos');
			return;
		}

		saveKeywordForPost(selectedPostId, keyword, response);
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
		console.log('Datos de publicaciones:', data); // Debugging

		if (data.status === 'success') {
			container.innerHTML = '';
			const posts = data.posts || [];

			if (posts.length === 0) {
				container.innerHTML = '<p>No hay publicaciones disponibles.</p>';
				return;
			}

			// Mostrar miniaturas
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
			showScreen('screen-details');
			// Limpiar contenedor antes de insertar nuevos elementos
			const dataContainer = document.getElementById('postDetail');
			dataContainer.innerHTML = `
                <button id="backToHomeBtn" class="btn-back">
                    <i class="fas fa-arrow-left"></i> Volver
                </button>
                <div class="post-detail">
                    <img id="detailThumbnail" src="${post.thumbnail}" 
                         alt="Publicación" 
                         style="max-width: 400px; border-radius: 10px;" 
                         onerror="this.src='/static/images/placeholder.jpg'">

                    <div class="post-info">
                        <h3>Caption Final:</h3>
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
                    </div>
					<div class="post-info">
					<h3>Agregar Palabra Clave</h3>
                        <input type="text" id="keywordInput" placeholder="Palabra clave...">
                        <textarea id="responseInput" rows="3" placeholder="Respuesta..."></textarea>
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
						alert('Completa ambos campos.');
						return;
					}
					saveKeywordForPost(post.id, keyword, response);
				});
		} else {
			detailContainer.innerHTML = `<p class="error">No se pudo cargar el post.</p>`;
		}
	} catch (error) {
		detailContainer.innerHTML = `<p class="error">Error de conexión: ${error.message}</p>`;
	}
}
