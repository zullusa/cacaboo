<?php extend('layouts/backend_layout'); ?>

<?php section('content'); ?>

<div class="container backend-page py-3" id="providers-page">
    <div class="row" id="providers">
        <div id="filter-providers" class="filter-records column col-12 mb-4">
            <button id="add-provider" class="btn btn-primary add-record-btn mb-4">
                <i class="fas fa-plus-square me-2"></i>
                <?= lang('add') ?>
            </button>

            <form class="mb-4">
                <div class="input-group">
                    <input type="text" class="key form-control" aria-label="keyword">

                    <button class="filter btn btn-outline-secondary" type="submit"
                            data-tippy-content="<?= lang('filter') ?>">
                        <i class="fas fa-search"></i>
                    </button>
                </div>
            </form>

            <h4 class="mb-3 fw-light">
                <?= lang('providers') ?>
            </h4>

            <div class="results overflow-auto" style="max-height: 650px;">
                <!-- JS -->
            </div>
        </div>

        <div class="record-details column col-12 mb-4">
            <div class="float-md-start mb-4 me-4">
                <div class="add-edit-delete-group btn-group">
                    <button id="edit-provider" class="btn btn-outline-secondary" disabled="disabled">
                        <i class="fas fa-edit me-2"></i>
                        <?= lang('edit') ?>
                    </button>
                </div>

                <div class="save-cancel-group" style="display:none;">
                    <button id="save-provider" class="btn btn-primary">
                        <i class="fas fa-check-square me-2"></i>
                        <?= lang('save') ?>
                    </button>
                    <button id="cancel-provider" class="btn btn-outline-secondary">
                        <?= lang('cancel') ?>
                    </button>
                    <button id="delete-provider" class="btn btn-outline-danger ms-2">
                        <i class="fas fa-trash-alt me-2"></i>
                        <?= lang('delete') ?>
                    </button>
                </div>
            </div>

            <div class="form-message alert mt-4" style="display:none;"></div>

            <div class="tab-content">
                <div class="details-view tab-pane fade show active clearfix" id="details">
                    <h4 class="mb-3 fw-light">
                        <?= lang('details') ?>
                    </h4>

                    <input type="hidden" id="id" class="record-id">

                    <div class="row">
                        <div class="details col-12 col-lg-6">
                            <div class="mb-3">
                                <label class="form-label" for="provider-name">
                                    <?= lang('provider_name') ?>
                                    <span class="text-danger">*</span>
                                </label>
                                <input id="provider-name" class="form-control required" maxlength="256" disabled>
                            </div>
                        </div>
                        <div class="settings col-12 col-lg-6">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <label class="form-label mb-0">
                                    <?= lang('services') ?>
                                </label>
                                <div class="btn-group btn-group-sm">
                                    <button type="button" id="select-all-services" class="btn btn-outline-secondary" disabled>
                                        <?= lang('select_all') ?>
                                    </button>
                                    <button type="button" id="select-none-services" class="btn btn-outline-secondary" disabled>
                                        <?= lang('select_none') ?>
                                    </button>
                                </div>
                            </div>

                            <div id="provider-services" class="card card-body border">
                                <!-- JS -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<?php end_section('content'); ?>

<?php section('scripts'); ?>

<script src="<?= asset_url('assets/js/http/providers_http_client.js') ?>"></script>
<script src="<?= asset_url('assets/js/pages/providers.js') ?>"></script>

<?php end_section('scripts'); ?>
