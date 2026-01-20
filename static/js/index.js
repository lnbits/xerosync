window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  delimiters: ['${', '}'],
  data: function () {
    return {
      settingsFormDialog: {
        show: false,
        data: {
          xero_client_id: null,
          xero_client_secret: null,
          xero_tax_standard: null,
          xero_tax_zero: null,
          xero_tax_exempt: null
        }
      },
      walletsFormDialog: {
        show: false,
        data: {
          wallet: null,
          push_payments: true,
          reconcile_name: null,
          reconcile_mode: null,
          xero_bank_account_id: null,
          tax_rate: null,
          notes: null
        }
      },
      walletsList: [],
      taxRateList: [
  { value: null,        label: 'Use Xero default for this account' },
  { value: 'standard',  label: 'Standard' },
  { value: 'zero',      label: 'Zero-rated (0%)' },
  { value: 'exempt',    label: 'Exempt / no tax' },
],
      accountCodeList: [],
      bankAccountList: [],
      walletsTable: {
        search: '',
        loading: false,
        columns: [
          {
            name: 'wallet',
            align: 'left',
            label: 'Wallet',
            field: 'wallet',
            sortable: true
          },
          {
            name: 'push_payments',
            align: 'left',
            label: 'Push payments',
            field: 'push_payments',
            sortable: true
          },
          {
            name: 'reconcile_name',
            align: 'left',
            label:
              'Auto-reconcile',
            field: 'reconcile_name',
            sortable: true
          },
          {
            name: 'reconcile_mode',
            align: 'left',
            label: 'Reconcile mode',
            field: 'reconcile_mode',
            sortable: true
          },
          {
            name: 'xero_bank_account_id',
            align: 'left',
            label:
              'Xero bank ID',
            field: 'xero_bank_account_id',
            sortable: true
          },
          {
            name: 'tax_rate',
            align: 'left',
            label: 'Tax rate',
            field: 'tax_rate',
            sortable: true
          },
          {
            name: 'last_synced',
            align: 'left',
            label: 'last_synced',
            field: 'last_synced',
            sortable: true
          },
          {
            name: 'status',
            align: 'left',
            label: 'status',
            field: 'status',
            sortable: true
          },
          {
            name: 'notes',
            align: 'left',
            label: 'Any notes',
            field: 'notes',
            sortable: true
          },
          {
            name: 'updated_at',
            align: 'left',
            label: 'Updated At',
            field: 'updated_at',
            sortable: true
          },
          {name: 'id', align: 'left', label: 'ID', field: 'id', sortable: true}
        ],
        pagination: {
          sortBy: 'updated_at',
          rowsPerPage: 10,
          page: 1,
          descending: true,
          rowsNumber: 10
        }
      }
    }
  },
  watch: {
    'walletsTable.search': {
      handler() {
        const props = {}
        if (this.walletsTable.search) {
          props['search'] = this.walletsTable.search
        }
        this.getWallets()
      }
    }
  },

  methods: {
    //////////////// Settings ////////////////////////
    async updateSettings() {
      try {
        const data = {...this.settingsFormDialog.data}

        await LNbits.api.request(
          'PUT',
          '/xerosync/api/v1/settings',
          null,
          data
        )
        this.settingsFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async getSettings() {
      try {
        const {data} = await LNbits.api.request(
          'GET',
          '/xerosync/api/v1/settings',
          null
        )
        this.settingsFormDialog.data = {
          ...this.settingsFormDialog.data,
          ...data
        }
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },
    async showSettingsDataForm() {
      await this.getSettings()
      this.settingsFormDialog.show = true
    },

    //////////////// Wallets ////////////////////////
    async showNewWalletsForm() {
      this.walletsFormDialog.data = {
        wallet: null,
        pull_payments: false,
        push_payments: true,
        reconcile_name: null,
        reconcile_mode: null,
        xero_bank_account_id: null,
        tax_rate: null,
        notes: null
      }
      await this.refreshXeroMetadata()
      this.walletsFormDialog.show = true
    },
    async showEditWalletsForm(data) {
      this.walletsFormDialog.data = {...data}
      await this.refreshXeroMetadata()
      this.walletsFormDialog.show = true
    },
    async saveWallets() {
      try {
        const data = {extra: {}, ...this.walletsFormDialog.data}
        const method = data.id ? 'PUT' : 'POST'
        const entry = data.id ? `/${data.id}` : ''
        await LNbits.api.request(
          method,
          '/xerosync/api/v1/wallets' + entry,
          null,
          data
        )
        this.getWallets()
        this.walletsFormDialog.show = false
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    },

    async getWallets(props) {
      try {
        this.walletsTable.loading = true
        const params = LNbits.utils.prepareFilterQuery(this.walletsTable, props)
        const {data} = await LNbits.api.request(
          'GET',
          `/xerosync/api/v1/wallets/paginated?${params}`,
          null
        )
        this.walletsList = data.data
        this.walletsTable.pagination.rowsNumber = data.total
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      } finally {
        this.walletsTable.loading = false
      }
    },
    async deleteWallets(walletsId) {
      await LNbits.utils
        .confirmDialog('Are you sure you want to delete this Wallets?')
        .onOk(async () => {
          try {
            await LNbits.api.request(
              'DELETE',
              '/xerosync/api/v1/wallets/' + walletsId,
              null
            )
            await this.getWallets()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async syncWallet(wallet) {
      await LNbits.utils
        .confirmDialog(
          'Push all current successful incoming payments for this wallet to Xero?'
        )
        .onOk(async () => {
          try {
            const {data} = await LNbits.api.request(
              'POST',
              `/xerosync/api/v1/wallets/${wallet.id}/push`,
              null
            )
            LNbits.utils.notifySuccess(data.message || 'Wallet pushed to Xero')
            await this.getWallets()
          } catch (error) {
            LNbits.utils.notifyApiError(error)
          }
        })
    },
    async exportWalletsCSV() {
      await LNbits.utils.exportCSV(
        this.walletsTable.columns,
        this.walletsList,
        'wallets_' + new Date().toISOString().slice(0, 10) + '.csv'
      )
    },

    //////////////// Xero metadata ////////////////////////
    async refreshXeroMetadata() {
      await Promise.all([this.getXeroAccounts(), this.getXeroBankAccounts()])
    },
    async getXeroAccounts() {
      try {
        const {data} = await LNbits.api.request('GET', '/xerosync/api/v1/accounts')
        this.accountCodeList = data
      } catch (error) {
        // User may not have connected to Xero yet; fail soft
        LNbits.utils.notifyError(
          'Could not load Xero accounts. Connect to Xero and try again.'
        )
        this.accountCodeList = []
      }
    },
    async getXeroBankAccounts() {
      try {
        const {data} = await LNbits.api.request('GET', '/xerosync/api/v1/bank_accounts')
        this.bankAccountList = data
      } catch (error) {
        LNbits.utils.notifyError(
          'Could not load Xero bank accounts. Connect to Xero and try again.'
        )
        this.bankAccountList = []
      }
    },

    //////////////// Utils ////////////////////////
    dateFromNow(date) {
      return moment(date).fromNow()
    },
        async connectToXero() {
      try {
        window.open('/xerosync/oauth/start', '_blank')
      } catch (error) {
        LNbits.utils.notifyApiError(error)
      }
    }
  },
  async created() {
    this.getWallets()
    this.getSettings()
    this.refreshXeroMetadata()
  }
})
