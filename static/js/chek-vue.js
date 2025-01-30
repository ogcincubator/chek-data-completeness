const { loadModule } = window['vue3-sfc-loader'];

const baseUrl = document.querySelector('#app').dataset.baseUrl;

const options = {
    moduleCache: {
        vue: Vue,
    },
    async getFile(url) {
        const componentUrl = new URL(`static/js/vue/${url}`, baseUrl);

        const res = await fetch(componentUrl);
        if ( !res.ok )
            throw Object.assign(new Error(res.statusText + ' ' + componentUrl), { res });
        return {
            getContentData: asBinary => asBinary ? res.arrayBuffer() : res.text(),
        }
    },
    addStyle(textContent) {
        const style = Object.assign(document.createElement('style'), { textContent });
        const ref = document.head.getElementsByTagName('style')[0] || null;
        document.head.insertBefore(style, ref);
    },
}

const vuetify = Vuetify.createVuetify({
});

const app = Vue.createApp({
    components: {
        'ChekDataCompleteness': Vue.defineAsyncComponent( () => loadModule('Main.vue', options) ),
    }
}).use(vuetify).mount('#app');
