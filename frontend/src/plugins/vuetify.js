import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'lightLab',
    themes: {
      lightLab: {
        dark: false,
        colors: {
          primary:      '#0e95a8',
          secondary:    '#0e95a8',
          warning:      '#c97a14',
          error:        '#d83a3a',
          success:      '#1f9d58',
          info:         '#2f6fda',
          background:   '#f4f5f7',
          surface:      '#ffffff',
          'on-surface': '#11161c',
        },
      },
    },
  },
})
