<?php
/**
 * Local variables.
 *
 * @var array $available_services
 * @var array $appointment_status_options
 * @var array $display_first_name
 * @var array $display_last_name
 * @var array $display_email
 * @var array $display_phone_number
 * @var array $display_address
 * @var array $display_city
 * @var array $display_zip_code
 * @var array $display_notes
 * @var array $require_first_name
 * @var array $require_last_name
 * @var array $require_email
 * @var array $require_phone_number
 * @var array $require_address
 * @var array $require_city
 * @var array $require_zip_code
 * @var array $require_notes
 */
?>
<div id="appointments-modal" class="modal fade">
    <div class="modal-dialog modal-dialog-centered modal-fullscreen-lg-down modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title"><?= lang('edit_appointment_title') ?></h3>
                <button class="btn-close" data-bs-dismiss="modal"></button>
            </div>

            <div class="modal-body">
                <div class="modal-message alert d-none"></div>

                <form>
                    <fieldset>
                        <h5 class="mb-3 fw-light"><?= lang('appointment_details_title') ?></h5>

                        <input id="appointment-id" type="hidden">

                        <div class="row">
                            <div class="col-12 col-sm-6">
                                <div class="mb-3">
                                    <label for="select-service" class="form-label">
                                        <?= lang('service') ?>
                                        <span class="text-danger">*</span>
                                    </label>
                                    <select id="select-service" class="required form-select">
                                        <?php
                                        // Group services by category, only if there is at least one service
                                        // with a parent category.
                                        $has_category = false;

                                        foreach ($available_services as $service) {
                                            if (!empty($service['service_category_id'])) {
                                                $has_category = true;
                                                break;
                                            }
                                        }

                                        if ($has_category) {
                                            $grouped_services = [];

                                            foreach ($available_services as $service) {
                                                if (!empty($service['service_category_id'])) {
                                                    if (!isset($grouped_services[$service['service_category_name']])) {
                                                        $grouped_services[$service['service_category_name']] = [];
                                                    }

                                                    $grouped_services[$service['service_category_name']][] = $service;
                                                }
                                            }

                                            // We need the uncategorized services at the end of the list, so we will use
                                            // another iteration only for the uncategorized services.
                                            $grouped_services['uncategorized'] = [];

                                            foreach ($available_services as $service) {
                                                if ($service['service_category_id'] == null) {
                                                    $grouped_services['uncategorized'][] = $service;
                                                }
                                            }

                                            foreach ($grouped_services as $key => $group) {
                                                $group_label =
                                                    $key !== 'uncategorized'
                                                        ? e($group[0]['service_category_name'])
                                                        : 'Uncategorized';

                                                if (count($group) > 0) {
                                                    echo '<optgroup label="' . $group_label . '">';

                                                    foreach ($group as $service) {
                                                        echo '<option value="' .
                                                            $service['id'] .
                                                            '">' .
                                                            e($service['name']) .
                                                            '</option>';
                                                    }

                                                    echo '</optgroup>';
                                                }
                                            }
                                        } else {
                                            foreach ($available_services as $service) {
                                                echo '<option value="' .
                                                    $service['id'] .
                                                    '">' .
                                                    e($service['name']) .
                                                    '</option>';
                                            }
                                        }
                                        ?>
                                    </select>
                                </div>

                                <div class="mb-3">
                                    <label for="select-provider" class="form-label">
                                        <?= lang('provider') ?>
                                        <span class="text-danger">*</span>
                                    </label>
                                    <select id="select-provider" class="required form-select"></select>
                                </div>

                                <div class="mb-3">
                                    <?php component('color_selection', ['attributes' => 'id="appointment-color"']); ?>
                                </div>

                                <div class="mb-3">
                                    <label for="appointment-status" class="form-label">
                                        <?= lang('status') ?>
                                    </label>
                                    <select id="appointment-status" class="form-select">
                                        <?php foreach ($appointment_status_options as $appointment_status_option): ?>
                                            <option value="<?= e($appointment_status_option) ?>">
                                                <?= e($appointment_status_option) ?>
                                            </option>
                                        <?php endforeach; ?>
                                    </select>
                                </div>

                                <div class="mb-3">
                                    <label for="appointment-author" class="form-label">
                                        <?= lang('author') ?>
                                    </label>
                                    <input type="text" id="appointment-author" class="form-control" readonly/>
                                </div>
                            </div>

                            <div class="col-12 col-sm-6">
                                <div class="mb-3">
                                    <label for="start-datetime"
                                           class="form-label"><?= lang('start_date_time') ?></label>
                                    <input id="start-datetime" class="required form-control">
                                </div>

                                <div class="mb-3">
                                    <label for="end-datetime" class="form-label"><?= lang('end_date_time') ?></label>
                                    <input id="end-datetime" class="required form-control">
                                </div>

                                <div class="mb-3">
                                    <label for="car-make" class="form-label">
                                        <?= lang('car_make') ?>
                                        <span class="text-danger">*</span>
                                    </label>
                                    <input type="text" id="car-make" class="required form-control" maxlength="255"/>
                                </div>

                                <div class="mb-3">
                                    <label for="car-plate" class="form-label">
                                        <?= lang('car_plate') ?>
                                        <span class="text-danger">*</span>
                                    </label>
                                    <input type="text" id="car-plate" class="required form-control" maxlength="255"/>
                                </div>

                                <div class="mb-3">
                                    <label for="appointment-notes" class="form-label">
                                        <?= lang('notes') ?>
                                        <?php if ($require_notes): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <textarea id="appointment-notes" class="<?= $require_notes
                                        ? 'required'
                                        : '' ?> form-control" rows="3"></textarea>
                                </div>
                            </div>
                        </div>
                    </fieldset>

                    <br>

                    <fieldset>
                        <h5 class="mb-3 fw-light">
                            <?= lang('customer_details_title') ?>
                            <button id="new-customer" class="btn btn-outline-secondary btn-sm" type="button"
                                    data-tippy-content="<?= lang('clear_fields_add_existing_customer_hint') ?>">
                                <i class="fas fa-plus-square me-2"></i>
                                <?= lang('new') ?>
                            </button>
                            <button id="select-customer" class="btn btn-outline-secondary btn-sm" type="button"
                                    data-tippy-content="<?= lang('pick_existing_customer_hint') ?>">
                                <i class="fas fa-hand-pointer me-2"></i>
                                <span>
                                    <?= lang('select') ?>
                                </span>
                            </button>

                            <input id="filter-existing-customers"
                                   placeholder="<?= lang('type_to_filter_customers') ?>"
                                   style="display: none;" class="input-sm form-control">
                        </h5>

                        <div id="existing-customers-list" style="display: none;"></div>

                        <input id="customer-id" type="hidden">

                        <div class="row">
                            <div class="col-12 col-sm-6">
                                <?php if ($display_first_name): ?>
                                <div class="mb-3">
                                    <label for="first-name" class="form-label">
                                        <?= lang('first_name') ?>
                                        <?php if ($require_first_name): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <input type="text" id="first-name"
                                           class="<?= $require_first_name ? 'required' : '' ?> form-control"
                                           maxlength="100"/>
                                </div>
                                <?php endif; ?>

                                <?php if ($display_last_name): ?>
                                <div class="mb-3">
                                    <label for="last-name" class="form-label">
                                        <?= lang('last_name') ?>
                                        <?php if ($require_last_name): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <input type="text" id="last-name"
                                           class="<?= $require_last_name ? 'required' : '' ?> form-control"
                                           maxlength="120"/>
                                </div>
                                <?php endif; ?>

                                <?php if ($display_email): ?>
                                <div class="mb-3">
                                    <label for="email" class="form-label">
                                        <?= lang('email') ?>
                                        <?php if ($require_email): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <input type="text" id="email"
                                           class="<?= $require_email ? 'required' : '' ?> form-control"
                                           maxlength="120"/>
                                </div>
                                <?php endif; ?>

                                <?php if ($display_phone_number): ?>
                                <div class="mb-3">
                                    <label for="phone-number" class="form-label">
                                        <?= lang('phone_number') ?>
                                        <?php if ($require_phone_number): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <div class="input-group">
                                        <span class="input-group-text">+7</span>
                                        <input type="text" id="phone-number" maxlength="10" inputmode="numeric"
                                               class="<?= $require_phone_number ? 'required' : '' ?> form-control"/>
                                    </div>
                                </div>
                                <?php endif; ?>

                                <?php component('custom_fields'); ?>

                            </div>
                            <div class="col-12 col-sm-6">
                                <?php if ($display_address): ?>
                                <div class="mb-3">
                                    <label for="address" class="form-label">
                                        <?= lang('address') ?>
                                        <?php if ($require_address): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <input type="text" id="address"
                                           class="<?= $require_address ? 'required' : '' ?> form-control"
                                           maxlength="120"/>
                                </div>
                                <?php endif; ?>

                                <?php if ($display_city): ?>
                                <div class="mb-3">
                                    <label for="city" class="form-label">
                                        <?= lang('city') ?>
                                        <?php if ($require_city): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <input type="text" id="city"
                                           class="<?= $require_city ? 'required' : '' ?> form-control"
                                           maxlength="120"/>
                                </div>
                                <?php endif; ?>

                                <?php if ($display_zip_code): ?>
                                <div class="mb-3">
                                    <label for="zip-code" class="form-label">
                                        <?= lang('zip_code') ?>
                                        <?php if ($require_zip_code): ?>
                                            <span class="text-danger">*</span>
                                        <?php endif; ?>
                                    </label>
                                    <input type="text" id="zip-code"
                                           class="<?= $require_zip_code ? 'required' : '' ?> form-control"
                                           maxlength="120"/>
                                </div>
                                <?php endif; ?>

                                <?php if ($display_notes): ?>
                                <div class="mb-3">
                                    <label for="customer-notes" class="form-label">
                                        <?= lang('notes') ?>
                                    </label>
                                    <textarea id="customer-notes" rows="3" class="form-control"></textarea>
                                </div>
                                <?php endif; ?>

                            </div>
                        </div>
                    </fieldset>

                </form>
            </div>

            <div class="modal-footer">

                <button class="btn btn-outline-secondary" data-bs-dismiss="modal">
                    <?= lang('cancel') ?>
                </button>
                <button id="save-appointment" class="btn btn-primary">
                    <i class="fas fa-check-square me-2"></i>
                    <?= lang('save') ?>
                </button>
            </div>
        </div>
    </div>
</div>

<?php section('scripts'); ?>

<script src="<?= asset_url('assets/js/components/appointments_modal.js') ?>"></script>

<?php end_section('scripts'); ?>
