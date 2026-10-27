// Adaptador de visor de documentos Heritage: para visores cuya barra muestra /d/<doc_id>/view?href=<id> y
// que cargan el manual en un iframe /d/<doc_id>/raw#<id>. Define window.HeritageViewer, que el script de navegación usa para el
// enlace copiado, la URL pública y el destino al cargar o con Atrás/Adelante del visor.
// Solo toca la URL del visor tras comprobar mismo origen y mismo documento; nunca lee ni cambia su DOM.
// En cualquier otro caso (otro origen, host no reconocido, otro documento) la navegación queda local y
// HeritageViewer.reason dice por qué la barra externa no se actualiza.
(function () {
  var VIEW_PATH = /^\/d\/([^/]+)\/view\/?$/;
  var RAW_PATH = /^\/d\/([^/]+)\/raw\/?$/;
  var TARGET_PARAM = 'href';
  var START_ID = 'top';

  function parseUrl(value) {
    try { return new URL(value, location.href); } catch (invalidUrlError) { return null; }
  }
  var shareMeta = document.querySelector('meta[name="heritage:share-url"]');
  var shareUrl = shareMeta && parseUrl(shareMeta.content);
  var shareMatch = shareUrl && shareUrl.pathname.match(VIEW_PATH);
  var ownMatch = location.pathname.match(RAW_PATH);

  // Mismo origen y mismo documento, o el motivo por el que no se puede sincronizar.
  function inspectViewer() {
    if (window.parent === window) return { reason: 'not-embedded' };
    if (!ownMatch) return { reason: 'unrecognized-document' };
    var viewerLocation;
    try {
      viewerLocation = window.parent.location;
      if (viewerLocation.origin !== location.origin) return { reason: 'cross-origin' };
    } catch (crossOriginError) {
      return { reason: 'cross-origin' };
    }
    var viewMatch = viewerLocation.pathname.match(VIEW_PATH);
    if (!viewMatch) return { reason: 'unrecognized-host' };
    if (viewMatch[1] !== ownMatch[1]) return { reason: 'different-document' };
    if (shareMatch && shareMatch[1] !== ownMatch[1]) return { reason: 'share-url-mismatch' };
    return { reason: 'synchronized', viewer: window.parent, documentId: ownMatch[1] };
  }
  var inspection = inspectViewer();
  var viewer = inspection.viewer || null;
  var limitationReported = false;
  function reportLimitation() {
    if (limitationReported || inspection.reason === 'not-embedded') return;
    limitationReported = true;
    console.warn('Heritage:documentViewer cannot update the viewer URL; navigation stays inside the manual', { reason: inspection.reason, documentId: ownMatch ? ownMatch[1] : null });
  }

  function publicUrl(id) {
    // Se conservan los demás parámetros de la URL pública (por ejemplo ?lang=pt): solo cambia el destino.
    var base = viewer ? parseUrl(viewer.location.origin + '/d/' + inspection.documentId + '/view' + viewer.location.search) : shareMatch ? parseUrl(shareUrl.origin + shareUrl.pathname + shareUrl.search) : null;
    if (!base) return null;
    if (id && id !== START_ID) base.searchParams.set(TARGET_PARAM, id); else base.searchParams.delete(TARGET_PARAM);
    return base.href;
  }

  window.HeritageViewer = {
    name: 'document-viewer',
    active: Boolean(viewer),
    reason: inspection.reason,
    // URL pública para copiar; null deja el formato genérico (<share-url>#<id>).
    shareUrl: function (id) { return publicUrl(id); },
    // Actualiza ?href= en la barra del visor sin agregar una entrada al historial.
    syncLocation: function (id) {
      if (!viewer) { reportLimitation(); return false; }
      var query = new URLSearchParams(viewer.location.search);
      if (id && id !== START_ID) query.set(TARGET_PARAM, id); else query.delete(TARGET_PARAM);
      var search = query.toString() ? '?' + query.toString() : '';
      // Un hash de sección heredado de un enlace viejo (…/view#faq) se quita: la URL pública dice solo el destino actual.
      var hash = viewer.location.hash;
      if (hash.length > 1 && document.getElementById(decodeURIComponent(hash.slice(1)))) hash = '';
      viewer.history.replaceState(viewer.history.state, '', viewer.location.pathname + search + hash);
      return true;
    },
    initialTargetId: function () {
      return viewer ? new URLSearchParams(viewer.location.search).get(TARGET_PARAM) : null;
    },
    // Atrás/Adelante en el visor: el manual va al destino de la URL pública.
    onNavigate: function (callback) {
      if (!viewer) return;
      viewer.addEventListener('popstate', function () { callback(new URLSearchParams(viewer.location.search).get(TARGET_PARAM) || START_ID); });
    }
  };
})();
