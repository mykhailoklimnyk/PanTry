import { mount } from 'svelte'

import '@fontsource-variable/manrope'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'

import App from './App.svelte'
import './styles/tokens.css'
import './styles/base.css'

const target = document.getElementById('app')
if (!target) throw new Error('#app не знайдено')

export default mount(App, { target })
